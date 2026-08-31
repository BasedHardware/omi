# WS Auth Rejection Severity — error-feed hygiene

Date: 2026-08-31 · Scope: `utils/other/endpoints.py` (`_verify_ws_auth`) ·
Guard tests: `tests/unit/test_ws_auth_rejection_logging.py`

## What happened

The GCP prod error feed (backend-listen) carried two of its top signatures
for 16+ consecutive hours on 2026-08-30/31:

```
ERROR:utils.other.endpoints:WebSocket auth failed: code=4001 error=Token expired, 1788101015 < 1788114388   (×9–47 / 30 min)
ERROR:utils.other.endpoints:WebSocket auth failed: code=4001 error=Certificate for key id 6ac9047f… not found.  (×1–34 / 30 min)
```

Both are **client-caused rejections the server handled correctly**:

- `Token expired` — samples show the presented Firebase ID tokens were 3.7h,
  7.5h and 18h past `exp` (tokens live 1h). Devices with suspended clocks or
  long sleep/reconnect loops replaying a dead credential.
- `Certificate for key id 6ac9047f… not found` — every sample across 14h
  names the *same* key id. Verified against Google's currently served x509
  set (`/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com`) on
  2026-08-31: that kid is **retired** — absent from the fresh cert list. A
  client cohort minted before the key rotation presents tokens no server can
  verify; note `google.oauth2.id_token.verify_token` checks the `kid` against
  the cert set *before* the `exp` check, so this fires regardless of expiry
  and for arbitrary freshness.

The rejections (and their close codes — 4001 "refresh" / 4004 "re-login") are
the auth protocol working. The **defect was classification**: every expected
client-caused rejection was logged at ERROR, so the stale-client reconnect
population was indistinguishable from a serving outage in the feed that pages
humans — during the same window a *real* outage (the Modulate STT 5xx storm)
had to be found inside it.

## The rule (severity follows fault origin)

In `_verify_ws_auth`, the narrow catch now routes logging through
`_log_ws_auth_rejection(close_code, error)`:

| Verify outcome | Fault origin | Severity | Close code |
|---|---|---|---|
| `InvalidIdTokenError` (incl. `ExpiredIdTokenError`, `RevokedIdTokenError`) | client — Firebase evaluated and refused the token | **WARNING** | unchanged (4001/4004/1008) |
| `CertificateFetchError` | **server** — could not fetch Google's certs to even evaluate | **ERROR** | 4001 |
| unexpected exception | server | ERROR | 1008 |

Close codes and reasons are untouched — clients already get the right
remediation hint. The warning message is `WebSocket auth rejected: …`
(still carries code + error text for debugging); server faults keep
`WebSocket auth failed: …`.

## Applying the same rule elsewhere

- Client-caused auth rejections should not be top error signatures. If a new
  one appears, first establish fault origin from samples (stale `exp` deltas,
  repeated retired `kid`s vs. cert-fetch/transport failures), then classify
  severity accordingly — do not mute by signature-silencing.
- The message-derived branches in `_get_ws_auth_close` (matching
  `'expired'`/`'certificate'` in the text) exist for exceptions crossing this
  boundary without a typed class; they do not change fault-origin
  classification.
- Related incident record and test fixtures:
  `tests/unit/test_ws_auth_rejection_logging.py` replays the exact prod
  message shapes.

Failure-Class: FC-request-input-rejection-escapes-as-server-fault (instance
fix; class canonized by #11853).
