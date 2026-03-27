import logging
import random
from typing import List, Optional

from config import PolicyConfig
from worker import Worker

from .policy import Policy

logger = logging.getLogger(__name__)


class PowerOfTwoPolicy(Policy):
    def __init__(self, config: PolicyConfig):
        self.config = config

    def name(self) -> str:
        return "power_of_two"

    def select_worker(
        self,
        workers: List[Worker],
        request_text: Optional[str] = None,
        headers: Optional[dict] = None,
    ) -> Optional[Worker]:
        _ = request_text
        _ = headers

        if len(workers) == 0:
            return None

        if len(workers) == 1:
            return workers[0]

        # Randomly sample two distinct workers.
        idx1, idx2 = random.sample(range(len(workers)), 2)
        load1 = workers[idx1].load()
        load2 = workers[idx2].load()

        if load1 <= load2:
            selected = idx1
        else:
            selected = idx2

        logger.debug(
            "[POLICY: %s ] random select %s and %s, select least load worker: %s",
            self.name(),
            workers[idx1],
            workers[idx2],
            workers[selected],
        )
        return workers[selected]
