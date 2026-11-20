"""Persistent lab environment for the pipeline lab (lane ``chain``).

Forked in spirit from ``testing/replay_harness/env.py``: the same loopback-only
emulator wiring and refusal of cloud clients, but persistent (nothing is deleted on
exit), with an explicit peer allowlist instead of "emulator only", the synthetic
identity ``local-dev-user``, a harness-owned wall clock and an overlay that pins
every serve-mode decision and logs it to ``decisions.jsonl``.

Nothing here constructs a client or touches the network at import time.
"""

LAB_UID = 'local-dev-user'
