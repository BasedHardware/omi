# Agent runtime shadow-state census

This is the ownership boundary for the desktop agent runtime convergence work.
It exists to keep a future change from creating another authoritative copy of a
runtime or turn state.

| Concern | Authoritative owner | Permitted projection |
| --- | --- | --- |
| Bridge lifecycle and start failure | `AgentRuntimeBridgeLifecycle` in `AgentRuntimeProcess` | Process/pipe handles are physical resources only. |
| Process liveness | `Process.isRunning` | `isAlive` and diagnostics snapshots. |
| Runtime protocol readiness | lifecycle `running` state | Negotiated protocol/version fields are handshake facts. |
| Chat send/stop authority | `ChatTurnLifecycle` in `ChatProvider` | UI `isSending` and error cards. |
| Canonical conversation and turn terminality | Node kernel journal | Swift journal callbacks and visible message blocks. |
| Context/cache identity | Node `ContextSnapshotProjection.contextPlan` | Swift typed decoder, PTT instruction and trace metadata. |
| Tool capabilities and provider availability | Node canonical tool manifest and adapter registry | Generated Swift surface definitions and typed setup-needed result. |

The reducer sequence fuzzer and runtime journal boundary test are the guard
against replaying a settled turn after crash, restart, mode switch, WAL stop,
or start failure. Do not add a boolean latch to mirror any row above; add a
physical resource fact or a derived projection instead.
