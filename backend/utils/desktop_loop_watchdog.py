"""Instance-local event-loop progress signal for the desktop backend."""

import asyncio
import logging
import os
import re
import sys
import threading
import time
from types import FrameType

from utils.executors import db_executor

logger = logging.getLogger(__name__)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.<>-]")


def _stack_path(frame: FrameType | None) -> str:
    """Only source locations, never source lines, arguments, or locals."""
    locations: list[str] = []
    while frame is not None and len(locations) < 40:
        code = frame.f_code
        filename = _SAFE_NAME.sub("_", os.path.basename(code.co_filename))[:80]
        function = _SAFE_NAME.sub("_", code.co_name)[:80]
        locations.append(f"{function}@{filename}:{frame.f_lineno}")
        frame = frame.f_back
    return " <- ".join(locations)


class DesktopLoopWatchdog:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.last_heartbeat = time.monotonic()
        self.in_flight = 0
        self._count_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop_thread_id: int | None = None
        self._reported = False

    def request_started(self) -> None:
        with self._count_lock:
            self.in_flight += 1

    def request_finished(self) -> None:
        with self._count_lock:
            self.in_flight -= 1

    def is_live(self) -> bool:
        return not self.enabled or time.monotonic() - self.last_heartbeat < 30

    async def heartbeat(self) -> None:
        while True:
            self.last_heartbeat = time.monotonic()
            await asyncio.sleep(1)

    def start(self) -> None:
        if not self.enabled:
            return
        self.last_heartbeat = time.monotonic()
        self._loop_thread_id = threading.get_ident()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="desktop-loop-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(1):
            self.check()

    def check(self, *, now: float | None = None) -> None:
        if not self.enabled:
            return
        delay = (time.monotonic() if now is None else now) - self.last_heartbeat
        if delay < 10:
            self._reported = False
            return
        if self._reported:
            return
        self._reported = True
        with self._count_lock:
            in_flight = self.in_flight
        frame = (
            sys._current_frames().get(self._loop_thread_id)  # type: ignore[reportPrivateUsage]
            if self._loop_thread_id is not None
            else None
        )
        logger.warning(
            "desktop_event_loop_stall delay_ms=%d db_active=%d db_queue=%d in_flight=%d stack=%s",
            int(delay * 1000),
            db_executor.active_count,
            db_executor._work_queue.qsize(),
            in_flight,
            _stack_path(frame),
        )


class InFlightRequestsMiddleware:
    def __init__(self, app, *, watchdog: DesktopLoopWatchdog) -> None:
        self.app = app
        self.watchdog = watchdog

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        self.watchdog.request_started()
        try:
            await self.app(scope, receive, send)
        finally:
            self.watchdog.request_finished()
