from models.memory_platform import MemoryPlatformCapability


def build_memory_platform_capability() -> MemoryPlatformCapability:
    return MemoryPlatformCapability()


__all__ = ["build_memory_platform_capability"]
