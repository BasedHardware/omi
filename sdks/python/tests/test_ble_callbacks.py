from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from omi.ble import listen, listen_payload
from omi.constants import PACKET_HEADER_BYTES


class CustomAwaitable:
    def __init__(self):
        self.awaited = False

    def __await__(self):
        async def _run():
            self.awaited = True

        return _run().__await__()


class MockBleakClient:
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.notify_handler = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def start_notify(self, char_uuid, handler):
        self.notify_handler = handler


def test_listen_awaits_futures_and_custom_awaitables():
    async def _test():
        client_instance = MockBleakClient("fake-device")
        loop = asyncio.get_running_loop()

        # 1. Direct Future: created inside callback and completed via call_soon.
        # If notify_handler awaits the future, fut.done() is True immediately after it returns.
        active_fut: asyncio.Future | None = None

        def future_handler(data: bytes):
            nonlocal active_fut
            active_fut = loop.create_future()
            loop.call_soon(active_fut.set_result, None)
            return active_fut

        # 2. Custom awaitable: must have __await__ executed.
        active_custom: CustomAwaitable | None = None

        def custom_handler(data: bytes):
            nonlocal active_custom
            active_custom = CustomAwaitable()
            return active_custom

        # 3. Direct asyncio.Task: must finish upon await.
        active_task: asyncio.Task | None = None

        def task_handler(data: bytes):
            nonlocal active_task

            async def _task_work():
                pass

            active_task = asyncio.create_task(_task_work())
            return active_task

        # 4. Standard coroutine
        coro_awaited = False

        async def coro_handler(data: bytes):
            nonlocal coro_awaited
            coro_awaited = True

        # 5. Sync callback
        sync_called = False

        def sync_handler(data: bytes):
            nonlocal sync_called
            sync_called = True

        handlers = [
            ("future", future_handler),
            ("custom", custom_handler),
            ("task", task_handler),
            ("coro", coro_handler),
            ("sync", sync_handler),
        ]

        with patch("omi.ble.BleakClient", return_value=client_instance):
            for name, handler in handlers:

                async def fake_sleep(_sec):
                    # Trigger notification handler
                    await client_instance.notify_handler("sender", bytearray(b"\x00\x01\x02\x03\x04"))
                    # If handler was an awaitable and not awaited, pending items won't be done yet
                    if name == "future":
                        assert active_fut is not None and active_fut.done(), "Future was not awaited"
                    elif name == "custom":
                        assert active_custom is not None and active_custom.awaited, "Custom awaitable was not awaited"
                    elif name == "task":
                        assert active_task is not None and active_task.done(), "Task was not awaited"
                    elif name == "coro":
                        assert coro_awaited, "Coroutine was not awaited"
                    elif name == "sync":
                        assert sync_called, "Sync handler was not called"
                    raise asyncio.CancelledError()

                with patch("asyncio.sleep", side_effect=fake_sleep):
                    try:
                        await listen("fake-device", handler)
                    except asyncio.CancelledError:
                        pass

    asyncio.run(_test())


def test_listen_payload_awaits_futures_and_custom_awaitables():
    async def _test():
        client_instance = MockBleakClient("fake-device")
        loop = asyncio.get_running_loop()

        # Future for payload
        active_fut: asyncio.Future | None = None

        def future_payload_handler(payload: bytes):
            assert payload == b"\x03\x04"
            nonlocal active_fut
            active_fut = loop.create_future()
            loop.call_soon(active_fut.set_result, None)
            return active_fut

        # Custom awaitable for payload
        active_custom: CustomAwaitable | None = None

        def custom_payload_handler(payload: bytes):
            assert payload == b"\x03\x04"
            nonlocal active_custom
            active_custom = CustomAwaitable()
            return active_custom

        # Task for payload
        active_task: asyncio.Task | None = None

        def task_payload_handler(payload: bytes):
            assert payload == b"\x03\x04"
            nonlocal active_task

            async def _task_work():
                pass

            active_task = asyncio.create_task(_task_work())
            return active_task

        handlers = [
            ("future", future_payload_handler),
            ("custom", custom_payload_handler),
            ("task", task_payload_handler),
        ]

        with patch("omi.ble.BleakClient", return_value=client_instance):
            for name, handler in handlers:

                async def fake_sleep(_sec):
                    packet = b"\x00" * PACKET_HEADER_BYTES + b"\x03\x04"
                    await client_instance.notify_handler("sender", bytearray(packet))
                    if name == "future":
                        assert active_fut is not None and active_fut.done(), "Payload Future was not awaited"
                    elif name == "custom":
                        assert (
                            active_custom is not None and active_custom.awaited
                        ), "Payload Custom awaitable was not awaited"
                    elif name == "task":
                        assert active_task is not None and active_task.done(), "Payload Task was not awaited"
                    raise asyncio.CancelledError()

                with patch("asyncio.sleep", side_effect=fake_sleep):
                    try:
                        await listen_payload("fake-device", handler)
                    except asyncio.CancelledError:
                        pass

    asyncio.run(_test())


@pytest.mark.parametrize("listen_fn", [listen, listen_payload])
def test_callback_exceptions_propagate(listen_fn):
    async def _test():
        client_instance = MockBleakClient("fake-device")
        loop = asyncio.get_running_loop()

        async def coro_handler(_data: bytes) -> None:
            raise ValueError("coro error")

        def future_handler(_data: bytes):
            fut = loop.create_future()
            loop.call_soon(fut.set_exception, ValueError("future error"))
            return fut

        class FailingAwaitable:
            def __await__(self):
                async def _run():
                    raise ValueError("custom error")

                return _run().__await__()

        def custom_handler(_data: bytes):
            return FailingAwaitable()

        def sync_handler(_data: bytes) -> None:
            raise ValueError("sync error")

        handlers = [
            ("sync", sync_handler, "sync error"),
            ("coro", coro_handler, "coro error"),
            ("future", future_handler, "future error"),
            ("custom", custom_handler, "custom error"),
        ]

        with patch("omi.ble.BleakClient", return_value=client_instance):
            for _name, handler, message in handlers:
                if listen_fn is listen_payload:
                    packet = b"\x00" * PACKET_HEADER_BYTES + b"\x03\x04"
                else:
                    packet = b"\x00\x01\x02\x03\x04"

                async def fake_sleep(_sec, expected_message=message, current_handler=handler):
                    with pytest.raises(ValueError, match=expected_message):
                        await client_instance.notify_handler("sender", bytearray(packet))
                    raise asyncio.CancelledError()

                with patch("asyncio.sleep", side_effect=fake_sleep):
                    try:
                        await listen_fn("fake-device", handler)
                    except asyncio.CancelledError:
                        pass

    asyncio.run(_test())
