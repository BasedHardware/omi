"""Keepalive budget for the internal listen ↔ pusher WebSocket lane.

Both ends of this lane are ours: backend-listen dials pusher's
``/v1/trigger/listen`` socket from ``utils/pusher.py``, and the pusher pod
accepts it behind uvicorn's ``--ws-ping-interval`` / ``--ws-ping-timeout``
flags. Whichever side declares the stricter keepalive decides when a
slow-but-alive peer is killed: a pong later than that side's budget fails the
connection with ``1011 "keepalive ping timeout"`` (websockets
``fail_connection(CloseCode.INTERNAL_ERROR, ...)``), and the observing session
tasks log the death once each.

Production ran that death 380-1227 times per hour across the fleet
(backend-listen, 2026-11-01, spread evenly over pods with no deploy
correlation): the server's 20s ping + 20s pong budget killed peers a
healthy client was still willing to wait 60s for. The values here are the
single source of truth for both ends so the two budgets can never drift
again — the client imports them for ``websockets.connect`` and the deploy
generator renders them into the pusher container command. A pod whose
event loop stalls briefly (CPU throttle, GC pause) now survives to send
its audio instead of being disconnected mid-window; a genuinely dead peer
still dies within the same order of magnitude it always did.
"""

from __future__ import annotations

# Seconds between keepalive pings on the internal lane. The client keeps the
# historical 30s cadence; the server's 20s cadence bought nothing — its only
# observable effect was a second, stricter death clock.
LISTEN_PUSHER_PING_INTERVAL_SECONDS = 30.0

# Seconds to wait for one keepalive pong before declaring the peer dead. This
# is the number that removes the churn: 60s is what the client already
# declared, so the server no longer kills a peer the client itself would have
# kept. The sum (interval + timeout) bounds how long a fully silent-but-alive
# peer can hold a socket open.
LISTEN_PUSHER_PING_TIMEOUT_SECONDS = 60.0

# Uvicorn spells both flags in integer seconds. Rendered into the pusher
# container command by scripts/generate_pusher_keepalive_flags.py; the
# client connect passes them to websockets.connect unchanged.
LISTEN_PUSHER_PING_INTERVAL_UVICORN = int(LISTEN_PUSHER_PING_INTERVAL_SECONDS)
LISTEN_PUSHER_PING_TIMEOUT_UVICORN = int(LISTEN_PUSHER_PING_TIMEOUT_SECONDS)


def uvicorn_keepalive_args() -> list[str]:
    """The ``--ws-ping-*`` argument list for the pusher container command."""
    return [
        f"--ws-ping-interval={LISTEN_PUSHER_PING_INTERVAL_UVICORN}",
        f"--ws-ping-timeout={LISTEN_PUSHER_PING_TIMEOUT_UVICORN}",
    ]
