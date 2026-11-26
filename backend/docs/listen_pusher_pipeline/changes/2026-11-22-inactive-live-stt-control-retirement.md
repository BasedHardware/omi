# Inactive live STT control retirement

SCA-3688 retires three controls with approved kill decisions.

- DEC-BTR-001 removes `PARAKEET_WINDOW_DIARIZATION` from serving configuration. Normal windowed sessions skip the window embedding path. The offline shape harness opts into speaker embedding explicitly.
- DEC-STT-006 removes `SONIOX_ELAPSED_AXIS` and its experimental elapsed map. Soniox places tokens against compact accepted sends. The wire ledger, independent capture-axis diagnostics, and the Modulate validation control remain available. See the [capture-axis contract](../../listen_pusher_pipeline.mdx#audio-timeline-v2-audio_timeline_v2-dev-only-until-promoted).
- DEC-STT-005 removes `STT_RESILIENT_RECONNECT`, its dedicated PCM ring, and its transport death typing. The strike-accounting fixes landed in [#22734](https://github.com/BasedHardware/omi/pull/22734) and [#23771](https://github.com/BasedHardware/omi/pull/23771). The [accepted replay contract](../../listen_pusher_pipeline.mdx#accepted-replay-sends-and-translator-coverage) still covers window recovery, cross-provider replacement, and demand switching.

The November 22 read-only production sample found the boolean flags false or absent and the elapsed-axis key absent on the inspected surfaces. The next normal backend release removes the declarations. Rollback uses a revert of [#26014](https://github.com/BasedHardware/omi/pull/26014).

The [window tests](../../../tests/unit/test_parakeet_window_live.py) exercise the offline embedding opt-in and shared replay. The [capture placement tests](../../../tests/unit/test_audio_timeline_segment_collapse.py) cover compact positioning across VAD gaps. The [wire ledger tests](../../../tests/unit/test_soniox_wire_ledger.py) and [transport diagnostics tests](../../../tests/unit/test_soniox_transport_diagnostics.py) cover the independent timing and close behavior.
