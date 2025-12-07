from typing import Optional, Callable, Any, Dict, List, TypeVar, Generic
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
import logging
import weakref
import gc

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class ResourceStats:
    created: int = 0
    released: int = 0
    active: int = 0
    leaked_warnings: int = 0
    last_gc: Optional[datetime] = None


class ResourceTracker:
    
    def __init__(self, name: str, warn_threshold: int = 100, gc_interval: int = 300):
        self.name = name
        self.warn_threshold = warn_threshold
        self.gc_interval = gc_interval
        self._active_resources: weakref.WeakSet = weakref.WeakSet()
        self._stats = ResourceStats()
        self._cleanup_callbacks: List[Callable] = []
    
    def register(self, resource: Any) -> None:
        self._active_resources.add(resource)
        self._stats.created += 1
        self._stats.active = len(self._active_resources)
        
        if self._stats.active > self.warn_threshold:
            logger.warning(
                f"ResourceTracker[{self.name}]: High resource count ({self._stats.active}). "
                f"Possible memory leak."
            )
            self._stats.leaked_warnings += 1
    
    def release(self, resource: Any) -> None:
        try:
            self._active_resources.discard(resource)
        except (TypeError, KeyError):
            pass
        
        self._stats.released += 1
        self._stats.active = len(self._active_resources)
    
    def add_cleanup_callback(self, callback: Callable) -> None:
        self._cleanup_callbacks.append(callback)
    
    async def force_cleanup(self) -> int:
        cleaned = 0
        
        for callback in self._cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
                cleaned += 1
            except Exception as e:
                logger.error(f"Cleanup callback failed: {e}")
        
        gc.collect()
        
        self._stats.last_gc = datetime.utcnow()
        self._stats.active = len(self._active_resources)
        
        return cleaned
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "created": self._stats.created,
            "released": self._stats.released,
            "active": self._stats.active,
            "leaked_warnings": self._stats.leaked_warnings,
            "last_gc": self._stats.last_gc.isoformat() if self._stats.last_gc else None
        }


class ManagedResource(Generic[T]):
    
    def __init__(
        self,
        create_func: Callable[[], T],
        cleanup_func: Optional[Callable[[T], None]] = None,
        tracker: Optional[ResourceTracker] = None
    ):
        self._create_func = create_func
        self._cleanup_func = cleanup_func
        self._tracker = tracker
        self._resource: Optional[T] = None
        self._created_at: Optional[datetime] = None
    
    @property
    def resource(self) -> T:
        if self._resource is None:
            self._resource = self._create_func()
            self._created_at = datetime.utcnow()
            if self._tracker:
                self._tracker.register(self._resource)
        return self._resource
    
    def release(self) -> None:
        if self._resource is not None:
            try:
                if self._cleanup_func:
                    self._cleanup_func(self._resource)
                if self._tracker:
                    self._tracker.release(self._resource)
            except Exception as e:
                logger.error(f"Error during resource cleanup: {e}")
            finally:
                self._resource = None
                self._created_at = None
    
    def __del__(self):
        self.release()


@asynccontextmanager
async def managed_async_resource(
    create_func: Callable,
    cleanup_func: Optional[Callable] = None,
    tracker: Optional[ResourceTracker] = None
):
    resource = None
    try:
        if asyncio.iscoroutinefunction(create_func):
            resource = await create_func()
        else:
            resource = create_func()
        
        if tracker:
            tracker.register(resource)
        
        yield resource
        
    finally:
        if resource is not None:
            try:
                if cleanup_func:
                    if asyncio.iscoroutinefunction(cleanup_func):
                        await cleanup_func(resource)
                    else:
                        cleanup_func(resource)
                
                if tracker:
                    tracker.release(resource)
                    
            except Exception as e:
                logger.error(f"Error during async resource cleanup: {e}")


@contextmanager
def managed_sync_resource(
    create_func: Callable,
    cleanup_func: Optional[Callable] = None,
    tracker: Optional[ResourceTracker] = None
):
    resource = None
    try:
        resource = create_func()
        
        if tracker:
            tracker.register(resource)
        
        yield resource
        
    finally:
        if resource is not None:
            try:
                if cleanup_func:
                    cleanup_func(resource)
                
                if tracker:
                    tracker.release(resource)
                    
            except Exception as e:
                logger.error(f"Error during sync resource cleanup: {e}")


_trackers: Dict[str, ResourceTracker] = {}


def get_tracker(name: str) -> ResourceTracker:
    if name not in _trackers:
        _trackers[name] = ResourceTracker(name)
    return _trackers[name]


def get_all_tracker_stats() -> List[Dict[str, Any]]:
    return [tracker.get_stats() for tracker in _trackers.values()]


async def cleanup_all_resources() -> Dict[str, int]:
    results = {}
    for name, tracker in _trackers.items():
        try:
            cleaned = await tracker.force_cleanup()
            results[name] = cleaned
        except Exception as e:
            logger.error(f"Failed to cleanup tracker {name}: {e}")
            results[name] = 0
    
    gc.collect()
    
    return results


class ConnectionPool(Generic[T]):
    
    def __init__(
        self,
        create_func: Callable[[], T],
        cleanup_func: Optional[Callable[[T], None]] = None,
        max_size: int = 10,
        max_idle_time: int = 300
    ):
        self._create_func = create_func
        self._cleanup_func = cleanup_func
        self._max_size = max_size
        self._max_idle_time = max_idle_time
        
        self._pool: List[tuple[T, datetime]] = []
        self._in_use: weakref.WeakSet = weakref.WeakSet()
        self._lock = asyncio.Lock()
        
        self._tracker = get_tracker(f"pool_{id(self)}")
    
    async def acquire(self) -> T:
        async with self._lock:
            now = datetime.utcnow()
            
            while self._pool:
                conn, last_used = self._pool.pop(0)
                
                if (now - last_used).total_seconds() > self._max_idle_time:
                    if self._cleanup_func:
                        try:
                            self._cleanup_func(conn)
                        except Exception:
                            pass
                    continue
                
                self._in_use.add(conn)
                return conn
            
            conn = self._create_func()
            self._in_use.add(conn)
            self._tracker.register(conn)
            
            return conn
    
    async def release(self, conn: T) -> None:
        async with self._lock:
            try:
                self._in_use.discard(conn)
            except (TypeError, KeyError):
                pass
            
            if len(self._pool) < self._max_size:
                self._pool.append((conn, datetime.utcnow()))
            else:
                if self._cleanup_func:
                    try:
                        self._cleanup_func(conn)
                    except Exception:
                        pass
                self._tracker.release(conn)
    
    async def cleanup_idle(self) -> int:
        async with self._lock:
            now = datetime.utcnow()
            cleaned = 0
            
            remaining = []
            for conn, last_used in self._pool:
                if (now - last_used).total_seconds() > self._max_idle_time:
                    if self._cleanup_func:
                        try:
                            self._cleanup_func(conn)
                        except Exception:
                            pass
                    self._tracker.release(conn)
                    cleaned += 1
                else:
                    remaining.append((conn, last_used))
            
            self._pool = remaining
            return cleaned
    
    @asynccontextmanager
    async def connection(self):
        conn = await self.acquire()
        try:
            yield conn
        finally:
            await self.release(conn)
