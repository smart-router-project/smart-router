# -*- coding: utf-8 -*-
"""BasicWorker implementation - concrete worker for HTTP backends."""

from __future__ import annotations

import threading
from smart_router.config import SmartRouterConfig
from smart_router.worker.core import (
    CircuitBreaker,
    WORKER_CLIENT,
    WorkerMetadata,
    WorkerType,
)
from smart_router.worker.core import Worker


class BasicWorker(Worker):
    """Basic worker implementation that represents a backend service.
    """

    def __init__(
        self,
        url: str,
        worker_type: WorkerType,
        config: SmartRouterConfig,
    ) -> None:
        self._metadata = WorkerMetadata(
            url=url, worker_type=worker_type, health_config=config.health_config
        )
        self._load_counter = 0
        self._healthy = True
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._circuit_breaker = CircuitBreaker(config.ciruit_breaker_config)
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return (
            f"BasicWorker(metadata={self._metadata}, healthy={self._healthy}, "
            f"circuit_breaker={self._circuit_breaker})"
        )

    # ===== Worker interface implementation =====

    def url(self) -> str:
        """Get the worker's URL."""
        return self._metadata.url

    def worker_type(self) -> WorkerType:
        """Get the worker's type."""
        return self._metadata.worker_type

    def is_healthy(self) -> bool:
        """Check if the worker is healthy."""
        with self._lock:
            return self._healthy

    def set_healthy(self, healthy: bool) -> None:
        """Set the worker's health status."""
        with self._lock:
            self._healthy = healthy

    def base_url(self) -> str:
        """Get the worker's identifier (includes @rank for DP workers)."""
        return self._metadata.url
    
    def endpoint_url(self, route):
        return f"{self.base_url()}{route}"

    async def check_health_async(self) -> None:
        """Perform an async health check on the worker."""
       
        base = self.base_url()
        health_url = f"{base}{self._metadata.health_config.endpoint}"
        timeout = self._metadata.health_config.timeout_secs
        try:
            r = await WORKER_CLIENT.get(health_url, timeout=timeout)
            healthy = r.status_code < 400
        except Exception:  # network error
            healthy = False


        # Update counters/health state
        with self._lock:
            if healthy:
                self._consecutive_failures = 0
                self._consecutive_successes += 1
                if (
                    not self._healthy
                    and self._consecutive_successes >= self._metadata.health_config.success_threshold
                ):
                    self._healthy = True
                    self._consecutive_successes = 0
            else:
                self._consecutive_successes = 0
                self._consecutive_failures += 1
                if (
                    self._healthy
                    and self._consecutive_failures >= self._metadata.health_config.failure_threshold
                ):
                    self._healthy = False
                    self._consecutive_failures = 0

        if healthy:
            return None
        else:
            raise ConnectionAbortedError(
                self._metadata.url,
                f"Health check failed (consecutive failures: {self._consecutive_failures})",
            )

    def load(self) -> int:
        """Get current load (number of active requests)."""
        with self._lock:
            return self._load_counter

    def increment_load(self, load: int = 1) -> None:
        """Increment the load counter."""
        with self._lock:
            self._load_counter += load

    def decrement_load(self, load: int = 1) -> None:
        """Decrement the load counter."""
        with self._lock:
            if self._load_counter > 0:
                self._load_counter -= load

    def decrement_load_with_context(self, load: int = 1):
        """Context manager to decrement load after the block, even if exceptions occur."""
        class LoadContextManager:
            def __enter__(inner_self):
                return self

            def __exit__(inner_self, exc_type, exc_val, exc_tb):
                self.decrement_load(load)

        return LoadContextManager()

    def reset_load(self) -> None:
        """Reset the load counter to 0."""
        with self._lock:
            self._load_counter = 0

    def metadata(self) -> WorkerMetadata:
        """Get worker metadata."""
        return self._metadata

    def circuit_breaker(self) -> CircuitBreaker:
        """Get the circuit breaker for this worker."""
        return self._circuit_breaker
