# Raw read outcomes

Raw reads expose `omi_audio_raw_read_total{result}` with closed outcomes `ok`,
`coverage_mismatch`, `checksum_mismatch`, `decode_error`, `decrypt_error`,
`identity_mismatch`, `no_pack`, and `other`. Failure logs contain only the bucket
and a closed codec; they omit object paths and exception text. Hash misses now
count explicitly. Coverage is `ok / (ok + failures)` over the ramp window.

No flag or rollout change. STOP_PCM remains off; its fidelity repair is separate.
The registry's near-zero raw-read failure gate now names this counter.
