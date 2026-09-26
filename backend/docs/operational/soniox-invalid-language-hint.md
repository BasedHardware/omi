# Soniox `Invalid language hint`: a config-shaped death masquerading as an idle timeout

Incident window: 2026-09-02 → 09-03 (backend-listen, Loop S sensor).
`ERROR:utils.stt.soniox:Soniox streaming error: 400 invalid_request Invalid
language hint.` appeared in essentially every 30-minute window for 6+ hours
(~16/24h), at a steady ×1–2-per-window cadence — the signature of a small set
of reconnecting sessions, not a fleet-wide outage.

## What was broken

Selection is honest about Soniox's core strength — "Soniox identifies the
language itself, so every requested language is serviceable" — but the client
then **told** the provider the language anyway:

- `process_audio_soniox` sent `language_hints: [<normalized base code>]` for
  every non-`multi` language, unvalidated. The provider validates that field
  against its documented vocabulary
  ([supported languages](https://soniox.com/docs/stt/concepts/supported-languages))
  and answers `400 invalid_request Invalid language hint` — **after** the
  WebSocket upgrade has already succeeded, so the death surfaces as an
  in-stream error frame, not a connect failure.
- A live example: `mt` (Maltese). The app accepts it as a user language (the
  batch Parakeet model lists it), Modulate's auto-detect table does not, so for
  that user Modulate is skipped, Soniox is selected, and the hint kills the
  socket at the config frame. The soniox branch's own fallbacks
  (`modulate_is_configured_fallback('mt')` → False, no Deepgram model for `mt`)
  are `None`, so the session dies with no provider left — on **every
  reconnect**, for as long as the user keeps the app open.
- The raw-string `'multi'` guard compared the *input* (`language != 'multi'`)
  while sending the *normalized* code, so a capitalized sentinel (`'Multi'`)
  normalized to `multi` and was sent as a literal hint — rejected the same way.
- `soniox_death_reason` mapped **every** 400 to `soniox_idle_timeout`, so these
  deaths were (a) logged at WARNING ("the protocol answering how the session
  was used") and (b) counted as VAD idle-timeouts in
  `omi_live_stt_terminal_failures_total` — a config bug wearing a usage-bug
  costume, invisible to the on-call.

## The contract now

| Concern | Behavior |
|---|---|
| Hint sent? | Only when the normalized base code is in `SONIOX_SUPPORTED_LANGUAGE_HINTS` (the documented vocabulary) |
| Unsupported language | No hint; `enable_language_identification` serves the session (auto-detect supports every language the model supports) + `record_fallback(component='stt_selection', from_mode='soniox_language_hint', to_mode='soniox_language_identification', reason='capability_mismatch', outcome='degraded')` — silent UX healing is allowed, silent ops is not |
| `'Multi'` / `'ja-JP'` / `'EN'` | Normalized before the sentinel comparison; no rejected entry can be sent |
| 400 frame carrying "Invalid language hint" | Typed `soniox_invalid_hint`, logged at **ERROR**, phase `initialization` |
| Other 400s | Still `soniox_idle_timeout` at WARNING (the VAD-starvation shape) |
| Selection circuit | Deliberately **not** opened: the provider is healthy; our config was wrong. Benching Soniox for everyone would convert one user's bad config into a fleet-wide provider skip |

## Why a static vocabulary and not the live Get-models endpoint

The list is the provider's documented, versioned page for the single unified
model (`stt-rt-v5`), fetched per deployment. Keeping it beside the other
capability tables in `config/stt_provider_policy.py` means a provider
vocabulary change is one reviewed change in the one module that already owns
provider capability — the same pattern as `MODULATE_SUPPORTED_LANGUAGES` and
`PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL`. The authenticated Get-models endpoint
would add a startup network dependency to selection for zero behavioral
difference today.

## Verification

- Unit: hint dropped for out-of-vocabulary codes with the fallback event fired;
  hint sent for in-vocabulary codes; `'Multi'`/`'ja-JP'` sent correctly;
  `soniox_death_reason(400, 'invalid_request', 'Invalid language hint.')` →
  `soniox_invalid_hint`; severity split; terminal-vocabulary registration.
- The sensor signature should collapse to zero once this ships; the residual
  `language_hints` traffic for supported languages is unchanged.
