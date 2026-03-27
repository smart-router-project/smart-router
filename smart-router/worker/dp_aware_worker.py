# -*- coding: utf-8 -*-
"""DPAwareWorker implementation - worker that handles data-parallel routing."""

from __future__ import annotations

from .basic_worker import BasicWorker
from config import SmartRouterConfig
from .core import (
    CircuitBreaker,
    WorkerMetadata,
    WorkerType,
)
from .core import Worker


class DPAwareWorker(Worker):
    """DP-aware worker that handles data-parallel routing.
    
    Wraps a BasicWorker and adds DP (data-parallel) specific behavior such as
    maintaining DP rank and size information.
    
    Note: The underlying BasicWorker is initialized with the base_url (without @rank).
    The @rank suffix is only used externally to identify this worker in the DP group.
    """

    def __init__(
        self,
        base_url: str,
        worker_type: WorkerType,
        config: SmartRouterConfig,
        dp_rank: int,
        dp_size: int,
    ) -> None:
        """Create a new DP-aware worker.
        
        Args:
            base_url: The base URL without DP suffix (passed to underlying BasicWorker)
            dp_rank: The rank of this worker in the DP group (0-indexed)
            dp_size: The total size of the DP group
            worker_type: The type of worker (Regular, Prefill, or Decode)
        """
        # BasicWorker initialized with clean base_url (no @rank)
        self._base_worker = BasicWorker(base_url, worker_type, config)
        self._base_url = base_url
        self._dp_rank = dp_rank
        self._dp_size = dp_size
        # Identifier for this worker in DP group (used externally)
        self._dp_id = f"{base_url}@{dp_rank}"

    def __repr__(self) -> str:
        return (
            f"BasicWorker(metadata={self._metadata}, healthy={self._healthy}, "
            f"circuit_breaker={self._circuit_breaker}, has_grpc_client={self._grpc_client is not None})"
        )

    def url(self) -> str:
        """Get the worker's identifier (includes @rank for DP workers)."""
        return self._dp_id

    def worker_type(self) -> WorkerType:
        """Get the worker's type."""
        return self._base_worker.worker_type()

    def is_healthy(self) -> bool:
        """Check if the worker is healthy."""
        return self._base_worker.is_healthy()

    def set_healthy(self, healthy: bool) -> None:
        """Set the worker's health status."""
        self._base_worker.set_healthy(healthy)

    async def check_health_async(self) -> None:
        """Perform an async health check on the worker."""
        return await self._base_worker.check_health_async()

    def load(self) -> int:
        """Get current load."""
        return self._base_worker.load()

    def increment_load(self, load: int = 1) -> None:
        """Increment the load counter."""
        self._base_worker.increment_load(load)

    def decrement_load(self, load: int = 1) -> None:
        """Decrement the load counter."""
        self._base_worker.decrement_load(load)

    def decrement_load_with_context(self, load = 1):
        return self._base_worker.decrement_load_with_context(load)

    def reset_load(self) -> None:
        """Reset the load counter to 0."""
        self._base_worker.reset_load()

    def metadata(self) -> WorkerMetadata:
        """Get worker metadata."""
        return self._base_worker.metadata()

    def circuit_breaker(self) -> CircuitBreaker:
        """Get the circuit breaker for this worker."""
        return self._base_worker.circuit_breaker()

    # ===== DP-aware specific methods (not part of Worker interface) =====

    def is_dp_aware(self) -> bool:
        """Check if this worker is DP-aware."""
        return True

    def base_url(self) -> str:
        """Get the base URL without DP suffix."""
        return self._base_url

    def dp_rank(self) -> int:
        """Get the DP rank of this worker."""
        return self._dp_rank

    def dp_size(self) -> int:
        """Get the total DP group size."""
        return self._dp_size

    def endpoint_url(self, route: str) -> str:
        """Get the actual endpoint URL for requests (uses base URL without @rank)."""
        return f"{self.base_url()}{route}"
