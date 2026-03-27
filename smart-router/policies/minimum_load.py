import logging
from .policy import Policy, PolicyConfig
from typing import Dict, Optional, List
from worker import Worker


class MinimumLoadPolicy(Policy):
    """Policy that selects the worker with the minimum load."""
    
    def __init__(self, config: PolicyConfig):
        pass

    def name(self) -> str:
        return "minimum_load"
    
    def select_worker(
        self,
        workers: List[Worker],
        request_text: Optional[str] = None,
        headers: Optional[dict] = None,
    ) -> Optional[Worker]:

        if len(workers) == 0:
            return None

        min_load = float('inf')
        selected_worker = None

        for worker in workers:
            load = worker.load()
            if load < min_load:
                min_load = load
                selected_worker = worker

        return selected_worker   