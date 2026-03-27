from dataclasses import dataclass


@dataclass
class HealthConfig:
    timeout_secs: int = 5
    check_interval_secs: int = 30
    endpoint: str = "/health"
    failure_threshold: int = 3
    success_threshold: int = 2


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    success_threshold: int = 1
    timeout_duration: float = 30.0  # seconds before moving from open -> half-open
    window_duration: float = 60.0  # sliding window (unused in simple version)
