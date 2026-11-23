# Ordered Soniox finalize clock is unreachable; SONIOX_ORDERED_FINALIZE ramp retired

On 2026-11-23, the finalize-padding probe (`backend/scripts/soniox_finalize_padding_probe.py`) ran live with a
non-customer key, synthetic speech and the production socket config. It found that neither `stt-rt-v5` nor
`stt-rt-v6` pads on finalize any more. The cases covered six offsets around the 1920-sample quantum, four mid-word
cuts, back-to-back finalizes and five finalizes in flight. Per model:

| model | `<fin>` acks: exact / either / padded-only | speech starts: exact / either / padded-only | law |
|---|---|---|---|
| `stt-rt-v5` | 26 / 1 / 0 | 4 / 2 / 0 | exact |
| `stt-rt-v6` | 26 / 1 / 0 | 4 / 2 / 0 | exact |

Each ack reported the exact sent cursor in whole milliseconds, and both models returned identical positions. The
`(floor(P / 1920) + 1) * 1920` law that `OrderedSonioxProviderClock` predicts was measured on v5 on 2026-10-06; it no
longer holds on either model. With `SONIOX_ORDERED_FINALIZE` on, every prediction would mismatch, and audio after
each finalize would become unplaceable.

## What changed

- `utils/stt/soniox.py` selects the ordered clock only when `SONIOX_MODEL` is in `ORDERED_FINALIZE_VALIDATED_MODELS`,
  and that set is empty. No model, v5 included, reaches the ordered clock even with the flag on. The wire ledger
  uses the reported clock, which reads each ack's position.
- The `SONIOX_ORDERED_FINALIZE` 1% ramp plan is retired: the registry entry is now `decision: kill`,
  `terminal: off`. The flag stays off everywhere, so serving behavior is unchanged. The registry grace ends
  2026-11-30. After that date the flag and its deploy declarations must be deleted unless the clock has been
  revalidated by then.
- The ordered-clock unit suites opt `stt-rt-v5` in through the set, so the dormant code stays covered.

## Before re-enabling

1. The probe must report `law: padded` for the target model on the production endpoint and socket config. Every
   ack must classify as padded, and every speech start as padded or either; none may be exact-only or other.
2. Only then add that model to `ORDERED_FINALIZE_VALIDATED_MODELS`, in a PR that carries the probe output.
3. Any enablement after that is a new ramp under the flag rules, with cohorts, the
   `omi_soniox_wire_ledger_controls_total` mismatch rate as the metric that must stay clean, an owner and a date.

See [the pipeline contract](../../listen_pusher_pipeline.mdx) (`SONIOX_ORDERED_FINALIZE`),
[the Soniox v6 note](2026-11-10-soniox-v6.md) and [the generated flag registry](../../feature-flag-registry.md).
