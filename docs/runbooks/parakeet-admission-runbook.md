# Parakeet Admission Control — Operational Runbook

**Owner:** `backend/config/parakeet_admission.py`
**Policy:** `backend/config/stt_provider_policy.py`
**Issue:** #10048

## Quick Mitigation (no code deploy)

| Scenario | Action | Effect |
|---|---|---|
| Parakeet overloaded / latency spike | Set `PARAKEET_ALLOCATION_PCT=0` on backend-listen GKE deployment | All traffic → Modulate immediately |
| Gradual canary | Set `PARAKEET_ALLOCATION_PCT=10` | ~10% of requests attempt Parakeet |
| Full Parakeet restore | Set `PARAKEET_ALLOCATION_PCT=100` (default) | Parakeet used when capacity allows |

## Parameters

| Env var | Default | Range | Effect |
|---|---|---|---|
| `PARAKEET_ALLOCATION_PCT` | `100` | `0–100` | % of requests eligible for Parakeet before capacity check |
| `PARAKEET_MAX_CONCURRENT` | `30` | `1–N` | Hard concurrent-stream cap per pod |

Both are read at *request* time — changes take effect on the next request with no restart.

## Routing Order

Modulate Velma-2 is the safe primary for all surfaces (streaming, pre-recorded, PTT). Parakeet is the bounded-capacity secondary. The STT selection path tries models in policy order; Parakeet passes through the admission gate before being selected. If denied (capacity full, allocation zero, allocation rejected, config incomplete, capability mismatch), the reason propagates to `record_fallback` with component `stt_selection` and outcome `degraded`.

## Monitoring

Watch the `omi_fallback_total` Prometheus counter filtered by:
- `component="stt_selection"`, `from_mode="parakeet"`, `to_mode="modulate"`
- `reason` in (`capacity_full`, `allocation_zero`, `allocation_rejected`)

Alert on sustained `capacity_full` (indicates the hard cap is too low or Parakeet is degraded).

## Counter Leak Safety

The admission counter increments in `try_admit()` and decrements in `release()`. `release()` is called unconditionally in each Parakeet socket's `drain_and_close()`. Since Parakeet sockets are only created when `try_admit()` returned `True`, every increment is paired with exactly one decrement. No counter leak path exists for Modulate-selected sessions.
