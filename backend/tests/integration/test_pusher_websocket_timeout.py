"""
Reproduce the pusher WebSocket connection drop caused by missing BackendConfig timeoutSec.

Production architecture:
  backend-listen → [GKE ILB] → pusher (Uvicorn 0.30.5)

The GKE ILB's timeoutSec (default 30s) is a backend response timeout that
doesn't count WebSocket control frames (ping/pong) as activity. During silence
(no audio data flowing), no data frames are exchanged, so the ILB kills the
connection after 30s. The fix is adding timeoutSec: 3600 to the BackendConfig.

Note: Uvicorn 0.30.5 already defaults to ws_ping_interval=20, so adding
--ws-ping-interval to the Dockerfile is a no-op.

Tests:
  1. timeoutSec=30, silence  → DIES at 30s  (reproduces the bug)
  2. timeoutSec=30, with data → SURVIVES     (data resets the timer)
  3. timeoutSec=3600, silence → SURVIVES     (the fix)

Usage:
    pip install uvicorn starlette websockets
    python3 scripts/test_pusher_ping.py
"""

import asyncio
import multiprocessing
import socket
import select
import sys
import threading
import time


def run_server(port: int):
    """Run a minimal Starlette WebSocket server via Uvicorn (with default ping settings)."""
    import uvicorn
    from starlette.applications import Starlette
    from starlette.routing import WebSocketRoute
    from starlette.websockets import WebSocket

    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_bytes()
                # Echo back to simulate transcription responses
                await websocket.send_bytes(data)
        except Exception:
            pass

    app = Starlette(routes=[WebSocketRoute("/ws", ws_endpoint)])
    uvicorn.run(app=app, host="127.0.0.1", port=port, log_level="warning")


def is_ws_data_frame(data: bytes) -> bool:
    """Check if a byte buffer starts with a WebSocket data frame (text or binary).
    Control frames (ping=0x9, pong=0xA, close=0x8) return False.
    Returns True for HTTP handshake traffic."""
    if len(data) < 2:
        return False
    if data[:4] == b'HTTP' or data[:3] == b'GET':
        return True
    opcode = data[0] & 0x0F
    return opcode in (0x0, 0x1, 0x2)


def run_ilb_proxy(listen_port: int, target_port: int, timeout_sec: int, stop_event: threading.Event):
    """TCP proxy simulating GKE ILB with timeoutSec.
    Only counts WebSocket DATA frames as activity (not ping/pong control frames)."""

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", listen_port))
    server.listen(5)
    server.settimeout(1.0)

    def handle_connection(client_sock):
        target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            target_sock.connect(("127.0.0.1", target_port))
        except Exception:
            client_sock.close()
            return

        last_data_activity = time.time()
        handshake_done = False

        while not stop_event.is_set():
            if handshake_done and (time.time() - last_data_activity) > timeout_sec:
                break

            readable, _, _ = select.select([client_sock, target_sock], [], [], 0.5)
            for sock in readable:
                try:
                    data = sock.recv(65536)
                    if not data:
                        client_sock.close()
                        target_sock.close()
                        return

                    if not handshake_done and b'101' in data[:20]:
                        handshake_done = True
                        last_data_activity = time.time()

                    if handshake_done and is_ws_data_frame(data):
                        last_data_activity = time.time()

                    if sock is client_sock:
                        target_sock.sendall(data)
                    else:
                        client_sock.sendall(data)
                except Exception:
                    client_sock.close()
                    target_sock.close()
                    return

        client_sock.close()
        target_sock.close()

    while not stop_event.is_set():
        try:
            client_sock, _ = server.accept()
            t = threading.Thread(target=handle_connection, args=(client_sock,), daemon=True)
            t.start()
        except socket.timeout:
            continue

    server.close()


def start_server_and_proxy(server_port, proxy_port, timeout_sec):
    """Start a Uvicorn server and ILB proxy. Returns (process, stop_event) to clean up."""
    p = multiprocessing.Process(target=run_server, args=(server_port,))
    p.start()
    time.sleep(1)

    stop = threading.Event()
    proxy = threading.Thread(
        target=run_ilb_proxy,
        args=(proxy_port, server_port, timeout_sec, stop),
        daemon=True,
    )
    proxy.start()
    time.sleep(0.5)
    return p, stop


def cleanup(process, stop_event):
    stop_event.set()
    process.terminate()
    process.join()


async def test_silence(port: int, label: str, timeout_secs: int):
    """Connect and send NO data frames (simulating silence). Tests if connection survives."""
    import websockets

    print(f"\n{'='*70}")
    print(f"  TEST: {label}")
    print(f"{'='*70}")
    print(f"  No data sent (simulating silence)")
    print(f"  Waiting up to {timeout_secs}s...\n")

    try:
        async with websockets.connect(
            f"ws://127.0.0.1:{port}/ws",
            ping_interval=30,
            ping_timeout=60,
        ) as ws:
            start = time.time()
            while time.time() - start < timeout_secs:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    elapsed = int(time.time() - start)
                    print(f"  [{elapsed:3d}s] Connection lost: {e}")
                    return False

                elapsed = int(time.time() - start)
                if elapsed > 0 and elapsed % 10 == 0:
                    print(f"  [{elapsed:3d}s] Connection alive")

            elapsed = int(time.time() - start)
            print(f"\n  [{elapsed:3d}s] Connection survived {timeout_secs}s!")
            return True

    except Exception as e:
        print(f"  Connection failed: {e}")
        return False


async def test_with_data(port: int, label: str, timeout_secs: int, send_interval: int = 10):
    """Connect and send data frames periodically (simulating audio). Tests if data keeps it alive."""
    import websockets

    print(f"\n{'='*70}")
    print(f"  TEST: {label}")
    print(f"{'='*70}")
    print(f"  Sending data every {send_interval}s (simulating audio)")
    print(f"  Waiting up to {timeout_secs}s...\n")

    try:
        async with websockets.connect(
            f"ws://127.0.0.1:{port}/ws",
            ping_interval=30,
            ping_timeout=60,
        ) as ws:
            start = time.time()
            last_send = start
            while time.time() - start < timeout_secs:
                # Send data periodically to simulate audio
                if time.time() - last_send >= send_interval:
                    await ws.send(b'\x00' * 640)  # Simulate audio chunk
                    last_send = time.time()

                try:
                    await asyncio.wait_for(ws.recv(), timeout=2)
                except asyncio.TimeoutError:
                    pass
                except Exception as e:
                    elapsed = int(time.time() - start)
                    print(f"  [{elapsed:3d}s] Connection lost: {e}")
                    return False

                elapsed = int(time.time() - start)
                if elapsed > 0 and elapsed % 10 == 0:
                    print(f"  [{elapsed:3d}s] Connection alive (data flowing)")

            elapsed = int(time.time() - start)
            print(f"\n  [{elapsed:3d}s] Connection survived {timeout_secs}s!")
            return True

    except Exception as e:
        print(f"  Connection failed: {e}")
        return False


def main():
    print("=" * 70)
    print("  PUSHER WEBSOCKET BUG REPRODUCTION")
    print("=" * 70)
    print()
    print("  Simulates GKE ILB behavior: only WebSocket data frames count")
    print("  as activity. Control frames (ping/pong) are ignored.")
    print("  Default timeoutSec=30 kills silent connections.")

    results = {}

    # --- Test 1: timeoutSec=30, silence → should FAIL ---
    print("\n\nStarting test 1: timeoutSec=30 + silence (expect FAIL at ~30s)...")
    p, stop = start_server_and_proxy(18091, 18081, 30)
    results['silence_30'] = asyncio.run(test_silence(18081, "timeoutSec=30 + silence (BUG)", timeout_secs=50))
    cleanup(p, stop)

    if not results['silence_30']:
        print("\n  CONFIRMED: Silent connection killed at ~30s")
    else:
        print("\n  UNEXPECTED: Connection survived")

    # --- Test 2: timeoutSec=30, with data → should PASS ---
    print("\n\nStarting test 2: timeoutSec=30 + data every 10s (expect PASS)...")
    p, stop = start_server_and_proxy(18092, 18082, 30)
    results['data_30'] = asyncio.run(
        test_with_data(18082, "timeoutSec=30 + data (control test)", timeout_secs=50, send_interval=10)
    )
    cleanup(p, stop)

    if results['data_30']:
        print("\n  CONFIRMED: Data frames keep ILB timer alive")
    else:
        print("\n  UNEXPECTED: Connection died despite data")

    # --- Test 3: timeoutSec=3600, silence → should PASS ---
    print("\n\nStarting test 3: timeoutSec=3600 + silence (expect PASS)...")
    p, stop = start_server_and_proxy(18093, 18083, 3600)
    results['silence_3600'] = asyncio.run(test_silence(18083, "timeoutSec=3600 + silence (FIX)", timeout_secs=50))
    cleanup(p, stop)

    if results['silence_3600']:
        print("\n  CONFIRMED: timeoutSec=3600 keeps silent connections alive")
    else:
        print("\n  UNEXPECTED: Connection died")

    # --- Summary ---
    print(f"\n{'='*70}")
    print(f"  RESULTS")
    print(f"{'='*70}")
    print(f"  1. timeoutSec=30  + silence:  {'DEAD at ~30s' if not results['silence_30'] else 'ALIVE (unexpected)'}")
    print(f"  2. timeoutSec=30  + data:     {'ALIVE' if results['data_30'] else 'DEAD (unexpected)'}")
    print(f"  3. timeoutSec=3600 + silence: {'ALIVE' if results['silence_3600'] else 'DEAD (unexpected)'}")

    all_pass = not results['silence_30'] and results['data_30'] and results['silence_3600']
    if all_pass:
        print(f"\n  All 3 tests passed! Bug reproduced and fix verified.")
    else:
        print(f"\n  Some tests had unexpected results.")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
