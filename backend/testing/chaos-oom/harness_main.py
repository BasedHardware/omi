"""
Chaos engineering harness — FastAPI app wrapping pusher.py with memory introspection.

Usage:
    PUSHER_MODULE=pusher_vuln uvicorn harness_main:app --host 0.0.0.0 --port 8080
    PUSHER_MODULE=pusher_fixed uvicorn harness_main:app --host 0.0.0.0 --port 8080
"""

import asyncio
import importlib
import os
import sys
import tracemalloc

# Add mock_deps to Python path so pusher.py's imports resolve to our mocks
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mock_deps'))

# Start tracemalloc for memory attribution
tracemalloc.start(10)

# Improvement #8: Monkeypatch asyncio.to_thread to track thread pool backlog
_orig_to_thread = asyncio.to_thread

to_thread_metrics = {
    'submitted': 0,
    'completed': 0,
    'in_flight': 0,
    'max_in_flight': 0,
}

# Limit thread pool to make backlog obvious
_max_workers = int(os.environ.get('TO_THREAD_WORKERS', '2'))
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=_max_workers)
asyncio.get_event_loop_policy()  # ensure loop policy exists


async def tracked_to_thread(func, /, *args, **kwargs):
    """Wrapper around asyncio.to_thread that tracks in-flight thread tasks."""
    to_thread_metrics['submitted'] += 1
    to_thread_metrics['in_flight'] += 1
    if to_thread_metrics['in_flight'] > to_thread_metrics['max_in_flight']:
        to_thread_metrics['max_in_flight'] = to_thread_metrics['in_flight']
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(_executor, lambda: func(*args, **kwargs))
        return result
    finally:
        to_thread_metrics['in_flight'] -= 1
        to_thread_metrics['completed'] += 1


asyncio.to_thread = tracked_to_thread

from fastapi import FastAPI

# Import the pusher module specified by environment variable
pusher_module_name = os.environ.get('PUSHER_MODULE', 'pusher_vuln')
pusher = importlib.import_module(pusher_module_name)

app = FastAPI()
app.include_router(pusher.router)

# Create temp dirs the original main.py creates
for path in ['_temp', '_samples', '_segments', '_speech_profiles']:
    os.makedirs(path, exist_ok=True)


@app.get('/health')
def health_check():
    return {"status": "healthy", "module": pusher_module_name}


@app.get('/debug/memory')
async def debug_memory():
    """Return current memory usage and top allocators for leak attribution."""
    import resource
    import gc

    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')

    # RSS from OS
    rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # Linux returns KB

    # Tracemalloc totals
    current, peak = tracemalloc.get_traced_memory()

    # Count asyncio tasks — async endpoint runs inside the event loop
    try:
        all_tasks = asyncio.all_tasks()
        task_count = len(all_tasks)
    except RuntimeError:
        task_count = -1

    # GC stats for allocator retention analysis
    gc_stats = gc.get_stats()

    # Improvement #2: safe_create_task metrics (vuln only — fixed uses spawn)
    task_metrics = {}
    try:
        from utils.other.task import get_task_metrics

        task_metrics = get_task_metrics()
    except (ImportError, AttributeError):
        pass

    # Improvement #4: Per-leak debug metrics from pusher module
    pusher_debug = getattr(pusher, 'debug_metrics', {})

    # Improvement #8: Thread pool backlog metrics
    thread_metrics = dict(to_thread_metrics)

    return {
        "rss_mb": round(rss_bytes / 1024 / 1024, 2),
        "traced_current_mb": round(current / 1024 / 1024, 2),
        "traced_peak_mb": round(peak / 1024 / 1024, 2),
        "asyncio_tasks": task_count,
        "gc_collections": [s.get('collections', 0) for s in gc_stats],
        "top_allocations": [
            {"file": str(stat.traceback), "size_kb": round(stat.size / 1024, 1), "count": stat.count}
            for stat in top_stats[:15]
        ],
        "module": pusher_module_name,
        "safe_create_task_metrics": task_metrics,
        "pusher_debug": pusher_debug,
        "to_thread_metrics": thread_metrics,
    }
