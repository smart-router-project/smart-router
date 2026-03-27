# -*- coding: utf-8 -*-
"""Worker base class and abstract interface."""

from __future__ import annotations

import asyncio

import enum
import threading
import time
from dataclasses import dataclass, field
from typing import Optional 
from config.worker import HealthConfig, CircuitBreakerConfig

import httpx


# shared client (httpx) for workers
WORKER_CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

@dataclass
class WorkerMetadata:
    """Metadata describing a worker, including its URL, type, and health check configuration."""
    url: str
    worker_type: WorkerType
    health_config: HealthConfig = field(default_factory=HealthConfig)

class WorkerType(str, enum.Enum):
    REGULAR = "regular"
    PREFILL = "prefill"
    DECODE = "decode"

    
class CircuitState(enum.Enum):
    """Enum representing the state of a circuit breaker."""
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2

class CircuitBreaker:
    """Simple circuit breaker implementation to track worker health and prevent requests to unhealthy workers."""
    def __init__(self, config: Optional[CircuitBreakerConfig] = None) -> None:
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._open_until: Optional[float] = None
        self._lock = threading.Lock()

    def _refresh_state_locked(self) -> None:
        """Refresh state transitions that depend on time. Caller must hold self._lock."""
        if self._state == CircuitState.OPEN and self._open_until is not None:
            if time.monotonic() >= self._open_until:
                self._state = CircuitState.HALF_OPEN
                self._failure_count = 0
                self._success_count = 0

    def state(self) -> CircuitState:
        with self._lock:
            self._refresh_state_locked()
            return self._state

    def can_execute(self) -> bool:
        with self._lock:
            self._refresh_state_locked()
            st = self._state
            return st != CircuitState.OPEN

    def record_outcome(self, success: bool) -> None:
        now = time.monotonic()
        with self._lock:
            self._refresh_state_locked()
            st = self._state
            if st == CircuitState.CLOSED:
                if success:
                    self._failure_count = 0
                else:
                    self._failure_count += 1
                    if self._failure_count >= self._config.failure_threshold:
                        self._state = CircuitState.OPEN
                        self._open_until = now + self._config.timeout_duration
            elif st == CircuitState.HALF_OPEN:
                if success:
                    self._success_count += 1
                    if self._success_count >= self._config.success_threshold:
                        self._state = CircuitState.CLOSED
                        self._failure_count = 0
                        self._success_count = 0
                else:
                    self._state = CircuitState.OPEN
                    self._open_until = now + self._config.timeout_duration
            # if OPEN, do nothing; transition happens in state()/can_execute()

    @classmethod
    def with_config(cls, config: CircuitBreakerConfig) -> "CircuitBreaker":
        return cls(config=config)

# ========================================================
## Worker interface and base implementation
# ========================================================
class Worker:
    """Abstract base class describing the worker interface.
    
    This class defines the contract that all worker implementations must follow.
    Concrete implementations include BasicWorker and DPAwareWorker.
    """

    def url(self) -> str:
        """Get the worker's URL."""
        raise NotImplementedError()

    def worker_type(self) -> WorkerType:
        """Get the worker's type (Regular, Prefill, or Decode)."""
        raise NotImplementedError()

    def is_healthy(self) -> bool:
        """Check if the worker is currently healthy."""
        raise NotImplementedError()

    def set_healthy(self, healthy: bool) -> None:
        """Set the worker's health status."""
        raise NotImplementedError()

    async def check_health_async(self) -> None:
        """Perform an async health check on the worker."""
        raise NotImplementedError()

    def check_health(self) -> None:
        """Synchronous health check wrapper (for compatibility)."""
        return asyncio.get_event_loop().run_until_complete(self.check_health_async())

    def load(self) -> int:
        """Get the current load (number of active requests)."""
        raise NotImplementedError()

    def increment_load(self, load: int = 1) -> None:
        """Increment the load counter."""
        raise NotImplementedError()

    def decrement_load(self, load: int = 1) -> None:
        """Decrement the load counter."""
        raise NotImplementedError()
    
    def decrement_load_with_context(self, load: int = 1):
        """Context manager to decrement load after the block, even if exceptions occur."""
        raise NotImplementedError()

    def reset_load(self) -> None:
        """Reset the load counter to 0 (for sync/recovery)."""
        pass

    def metadata(self) -> WorkerMetadata:
        """Get worker-specific metadata."""
        raise NotImplementedError()

    def circuit_breaker(self) -> CircuitBreaker:
        """Get the circuit breaker for this worker."""
        raise NotImplementedError()

    def is_available(self) -> bool:
        """Check if the worker is available (healthy + circuit closed/half-open)."""
        return self.is_healthy() and self.circuit_breaker().can_execute()

    # ===== Convenience helpers for metadata labels =====

    def model_id(self) -> str:
        """Get the model ID this worker serves."""
        return self.metadata().labels.get("model_id", "unknown")
    
    def endpoint_url(self, route: str) -> str:
        """Get the actual endpoint URL for requests (uses base URL without @rank)."""
        raise NotImplementedError()
    
    def base_url(self) -> str:
        """Get the base URL without DP suffix."""
        raise NotImplementedError()

    
    # ===== DP-aware specific methods (not part of Worker interface) =====
    def is_dp_aware(self) -> bool:
        """Check if this worker is DP-aware (data-parallel aware)."""
        return False

    def dp_rank(self) -> int:
        """Get the DP rank of this worker."""
        if self.is_dp_aware():
            raise NotImplementedError("DP-aware workers must implement dp_rank()")

    def dp_size(self) -> int:
        """Get the total DP group size."""
        if self.is_dp_aware():
            raise NotImplementedError("DP-aware workers must implement dp_size()")

