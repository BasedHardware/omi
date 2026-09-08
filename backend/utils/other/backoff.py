import random


def calculate_backoff_with_jitter(attempt: int, base_delay: int = 1000, max_delay: int = 32000) -> float:
    jitter = random.random() * base_delay
    backoff = min(((2**attempt) * base_delay) + jitter, max_delay)
    return backoff
