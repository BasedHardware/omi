import asyncio


def safe_create_task(t):
    task = asyncio.create_task(t)
    task.add_done_callback(
        lambda l: print("Unhandled exception in background task:", l.exception()) if l.exception() else None
    )
    return task
