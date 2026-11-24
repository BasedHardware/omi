# Hermetic lifecycle simulator

WP-A adds emulator-backed lifecycle fixtures for sealed-record registration,
record-pending admission, failed-upload retry and dead-producer sealing.
Synthetic server-batch cases also exercise finalization/results and
audio-close/completion ordering through real durable leases and transactions.
The existing listen/pusher gauntlet runs the scenarios through its existing
runner chain. Production entrypoints and lifecycle behavior are unchanged.

The positive control uses the real batch custody, scheduler, merge,
projection and recovery processing paths with synthetic provider leaves.
Expected leak failures accept only final lifecycle invariant assertions;
transport, fixture and proof failures cannot be swallowed by xfail.

See [the simulator README](../../../testing/lifecycle_sim/README.md) for local
commands, fake-clock helpers, fault boundaries and the WP-B fixture API.
This is local/emulator and CI evidence; no deploy or feature ramp is needed.
