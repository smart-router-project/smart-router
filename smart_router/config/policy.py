import logging
from dataclasses import dataclass, field

@dataclass
class PolicyConfig:

    policy: str = "round_robin"  # default policy

    cache_threshold: float = 0.5

    balance_abs_threshold: int = 5

    balance_rel_threshold: float = 2.0
    

    