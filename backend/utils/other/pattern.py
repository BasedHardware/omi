from typing import Any, Callable, TypeVar

T = TypeVar("T")


def singleton(cls: Callable[..., T]) -> Callable[..., T]:
    instances: dict[Any, T] = {}

    def get_instance(*args: Any, **kwargs: Any) -> T:
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance
