# -*- coding: utf-8 -*-
"""Worker registry and collection helper functions.

Provides centralized registry for workers with model-based indexing, enabling
efficient multi-router support and worker management.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import TYPE_CHECKING, Dict, List, Optional
from .core import  WorkerType, WorkerType, Worker

logger = logging.getLogger()

# ===== Worker ID =====
class WorkerId:
    """Unique identifier for a worker."""

    def __init__(self, id_str: Optional[str] = None) -> None:
        """Create a new worker ID."""
        self._id = id_str or str(uuid.uuid4())

    @staticmethod
    def new() -> WorkerId:
        """Create a new worker ID."""
        return WorkerId()

    @staticmethod
    def from_string(s: str) -> WorkerId:
        """Create a worker ID from a string."""
        return WorkerId(s)

    def as_str(self) -> str:
        """Get the ID as a string."""
        return self._id

    def __str__(self) -> str:
        """String representation."""
        return self._id

    def __repr__(self) -> str:
        """Representation."""
        return f"WorkerId({self._id})"

    def __hash__(self) -> int:
        """Hash."""
        return hash(self._id)

    def __eq__(self, other: object) -> bool:
        """Equality check."""
        if isinstance(other, WorkerId):
            return self._id == other._id
        return False

    def __lt__(self, other: WorkerId) -> bool:
        """Less than for sorting."""
        return self._id < other._id


# ===== Worker Registry =====


class WorkerRegistry:
    """Worker registry with model-based indexing for multi-router support."""

    def __init__(self) -> None:
        """Create a new worker registry."""
        self._workers: Dict[WorkerId, Worker] = {}
        self._type_workers: Dict[WorkerType, List[WorkerId]] = {}
        self._url_to_id: Dict[str, WorkerId] = {}
        self._lock = threading.RLock()

    def register(self, worker: Worker) -> WorkerId:
        """Register a new worker and return its unique ID."""
        with self._lock:
            # Check if worker with this URL already exists
            if worker.url() in self._url_to_id:
                worker_id = self._url_to_id[worker.url()]
            else:
                worker_id = WorkerId.new()

            # Store worker
            self._workers[worker_id] = worker

            # Update URL mapping
            self._url_to_id[worker.url()] = worker_id

            # Update type index
            worker_type_key = worker.worker_type()
            if worker_type_key not in self._type_workers:
                self._type_workers[worker_type_key] = []
            self._type_workers[worker_type_key].append(worker_id)

            return worker_id

    def remove(self, worker_id: WorkerId) -> Optional[Worker]:
        """Remove a worker by ID."""
        with self._lock:
            if worker_id not in self._workers:
                return None

            worker = self._workers.pop(worker_id)

            # Remove from URL mapping
            self._url_to_id.pop(worker.url(), None)

            # Remove from type index
            worker_type_key = worker.worker_type()
            if worker_type_key in self._type_workers:
                self._type_workers[worker_type_key] = [
                    id for id in self._type_workers[worker_type_key] if id != worker_id
                ]
                if not self._type_workers[worker_type_key]:
                    del self._type_workers[worker_type_key]

            return worker

    def remove_by_url(self, url: str) -> Optional[Worker]:
        """Remove a worker by URL."""
        with self._lock:
            if url in self._url_to_id:
                worker_id = self._url_to_id[url]
                return self.remove(worker_id)
            return None

    def get(self, worker_id: WorkerId) -> Optional[Worker]:
        """Get a worker by ID."""
        with self._lock:
            return self._workers.get(worker_id)

    def get_by_url(self, url: str) -> Optional[Worker]:
        """Get a worker by URL."""
        with self._lock:
            if url in self._url_to_id:
                return self._workers.get(self._url_to_id[url])
            return None

    def get_by_type(self, worker_type: WorkerType) -> List[Worker]:
        """Get all workers by worker type."""
        with self._lock:
            worker_ids = self._type_workers.get(worker_type, [])
            return [self._workers[id] for id in worker_ids if id in self._workers]
    
    def get_healthy_by_type(self, worker_type: WorkerType) -> List[Worker]:
        with self._lock:
            worker_ids = self._type_workers.get(worker_type, [])
            # return [self._workers[id] for id in worker_ids if id in self._workers and self._workers[id].is_healthy()]
            return [self._workers[id] for id in worker_ids if id in self._workers]

    def get_all(self) -> List[Worker]:
        """Get all workers."""
        with self._lock:
            return list(self._workers.values())

    def get_all_with_ids(self) -> List[tuple[WorkerId, Worker]]:
        """Get all workers with their IDs."""
        with self._lock:
            return [(id, worker) for id, worker in self._workers.items()]

    def get_all_urls(self) -> List[str]:
        """Get all worker URLs."""
        with self._lock:
            return [worker.url() for worker in self._workers.values()]

    def __repr__(self) -> str:
        """String representation."""
        with self._lock:
            total_workers = len(self._workers)

            healthy_count = 0
            total_load = 0
            regular_count = 0
            prefill_count = 0
            decode_count = 0

            for worker in self._workers.values():
                if worker.is_healthy():
                    healthy_count += 1
                total_load += worker.load()

                worker_type = worker.worker_type()
                if worker_type == WorkerType.REGULAR:
                    regular_count += 1
                elif worker_type == WorkerType.PREFILL:
                    prefill_count += 1
                elif worker_type ==  WorkerType.DECODE:
                    decode_count += 1

            return  (
            f"WorkerRegistryStats("
            f"total={total_workers}, "
            f"load={total_load}, "
            f"healthy={healthy_count},"
            f"regular={regular_count}, "
            f"prefill={prefill_count}, "
            f"decode={decode_count})"
            )


def get_healthy_workers(workers: List[Worker]) -> List[Worker]:
    """Helper function to filter healthy workers."""
    return [worker for worker in workers if worker.is_healthy()]

def get_available_workers(workers: List[Worker]) -> List[Worker]:
    """Helper function to filter available workers (healthy and circuit breaker allows)."""
    return [worker for worker in workers if worker.is_available()]
