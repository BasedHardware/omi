from models.memory_platform import MemoryPlatformCapability


def build_memory_platform_capability() -> MemoryPlatformCapability:
    return MemoryPlatformCapability()


def memory_platform_capability() -> MemoryPlatformCapability:
    return build_memory_platform_capability()


__all__ = ["build_memory_platform_capability", "memory_platform_capability"]
