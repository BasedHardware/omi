# Track 2 ground truth: PTT context-vocabulary boosting + `/v2/voice-message/transcribe` contract

Extracted directly from source (frozen Mac tag v0.12.72 at `.worktrees/mac-ref`, backend at
`.worktrees/track2-voice-bar/backend`). All claims are file:line cited. Where the assignment
brief asserted something ("stt_provider/stt_model NEW fields", "stt_provider_configuration_error
503") that does not exist in source, that is called out explicitly below — **do not build against
those assumed facts.**

---

## 1. Mac's keyword collection (PTTContextVocabularyProvider.swift)

File: `desktop/macos/Desktop/Sources/FloatingControlBar/PTTContextVocabularyProvider.swift`

Three sources, collected into one capped, deduped list (`KeywordCollector`, `limit = maxKeywords = 100`, case-insensitive dedup, 2-80 char terms, stopword-filtered):

1. **User-configured vocabulary** (`AssistantSettings.shared.effectiveVocabulary`, line 22-24) — backend-synced custom terms (`PATCH` via `APIClient.updateTranscriptionPreferences(vocabulary:)`, `APIClient.swift:4261`; backend route lives in `backend/routers/users.py`). Added first (highest collector priority since collector fills in insertion order and stops at the cap).
2. **Immediate OCR of the active window** (`captureImmediateScreenText`, line 77-117) — prefers a pre-overlay display image if the caller supplied one (avoids an extra capture), else OCRs the active window (skipping it if the active app is Omi itself, line 87/98-100) or falls back to whole-screen capture. Capped to `maxImmediateOCRLength = 2_000` chars (line 33) before extraction. Two passes: `addExtractedTerms(priority: true)` (capitalized-word/acronym patterns) then `addVisibleTerms` (any word ≥2 chars).
3. **Recent-activity Rewind screenshots** (`loadRecentActivityScreenshots`, line 63-75) — `RewindDatabase.shared.getScreenshots(from: date-120s, to: date+2s, limit: 12)`. `lookbackSeconds = 120` (line 17). For each screenshot: app name added (`collector.add`), window title added both raw and as extracted terms (priority), OCR text (capped `maxTextLengthPerScreenshot = 3_000` chars, line 15) added as non-priority extracted terms.

Cap/dedup mechanics (`KeywordCollector`, line 501-564): `limit = 100`, lowercase dedup, term length 2-80 chars, must contain a letter, filtered against a ~40-word stopword list (line 502-508, e.g. "voice", "user", "chat", "text", "task"...).

**A second, independent re-sanitization happens client-side before the term list ever reaches the wire** — `TranscriptionService.sanitizedContextKeywords` (`TranscriptionService.swift:124-157`): re-tokenizes every keyword with `\b[A-Za-z][A-Za-z'\-]{1,31}\b`, applies its own (slightly different) stopword list, dedups case-insensitively, and hard-caps at **40** terms (line 151-153) — well under the backend's 100-term cap. It also unconditionally prepends `"Omi", "OMI"` (line 134) so the brand name always survives. So the *effective* outgoing cap Mac ever sends is 40, not 100.

## 2. PTTTranscriptContextualCorrector (deterministic post-STT correction)

Same file, line 139-388. Runs **after** the backend returns a transcript, entirely client-side — this is not a backend/STT-time correction and has no server-side analog.

- `correctCommonPTTPhrases` — one hardcoded fix: `"Home are you"` → `"How are you"`.
- `correctOmiBrand` — regex `\b(?:omi|omni|omie|omy|ohmi|oh me)\b` (case-insensitive) → `"Omi"`.
- `correctDirectedNameObject` / `correctGreetingTarget` — regex-detects a greeting/addressed-name pattern (`"say hi to X"`, `"hey X, ..."`) and, if a keyword from the captured vocabulary is phonetically/edit-distance close (Levenshtein + suffix/phonetic-tail heuristics, `greetingTargetScore`, line 248-290; thresholds e.g. exact-collapsed-match=124, prefix-distance-0=120, edit-distance≤2=100-distance, shared-suffix≥3=72, phonetic-tail-match=68), replaces the mis-transcribed name with the canonical keyword. `canonicalNameTerm` (line 354-366) restricts candidates to `^[A-Za-z][A-Za-z'\-]{2,31}$`, non-stopword, and rejects all-caps ≤4-char tokens except "OMI".
- Separately, `PTTTranscriptCleanupService` (line 390-499, an `actor`) is an **optional Gemini-based cleanup pass** (2s timeout, `ModelQoS.Gemini.proactive`) that also takes context terms (its own extraction, capped `maxContextTerms = 40`) and asks an LLM to fix obvious ASR errors using those terms as hints. This is a *separate, LLM-backed* correction layer beyond the deterministic regex corrector — confirm with the team whether Windows needs to port this too or whether the deterministic corrector alone is in scope (not decided in this brief; flagging as a scope question, not blocking).

**Portability to Windows:** all three keyword sources have Windows equivalents already wired for *other* features:
- User vocabulary: `desktop/windows/src/renderer/src/components/settings/tabs/TranscriptionTab.tsx` + `omiApi.generated.ts` already talk to the same backend vocabulary endpoint.
- Immediate OCR: `window.omi.screenReadText()` (`desktop/windows/src/renderer/src/lib/screenContext.ts:24`, owned by Track 1 — consume only, do not edit).
- Recent-activity screenshots: `window.omi.rewindFrames(from, to)` → `RewindFrame { ts, app, windowTitle, processName, ocrText, ... }` (`desktop/windows/src/shared/types.ts:616,1124-1135`) — directly analogous to `RewindDatabase.getScreenshots`, just slice/limit client-side (no `limit` param on the IPC call itself).
The deterministic `PTTTranscriptContextualCorrector` regex logic is pure TS-portable (no Swift-only dependency) if Track 2 wants to port it into `transport.ts`/a new module — not requested by this brief, noting only.

---

## 3. `/v2/voice-message/transcribe` — exact contract (verified directly in `backend/routers/chat.py`)

**Confirmed: the batch endpoint is `POST /v2/voice-message/transcribe`** (`chat.py:569`), matching Windows' `BATCH_TRANSCRIBE_PATH` constant already. There is a *separate* WebSocket endpoint `/v2/voice-message/transcribe-stream` (`chat.py:769`) for the opportunistic live-interim lane — both exist; the brief's caution about "-stream" was already correctly avoided by both Mac's batch path and Windows' `transport.ts`.

### Request (desktop PTT path: `application/octet-stream`, `chat.py:591-648`)

- **Body:** raw PCM bytes (`request.body()`), NOT multipart. Content-Type must contain `application/octet-stream`. Hard cap `_MAX_PCM_BODY_BYTES = 200_000_000` (200 MB, `chat.py:90`) — checked from `Content-Length` first (early 413) and again after buffering.
- **Query params** (all optional except body):
  - `language` — resolved via `resolve_voice_message_language(uid, language)` if absent/empty.
  - `keywords` — comma-separated string, parsed by `_parse_context_keywords` (`chat.py:124-141`): splits on `,`, trims, drops terms <2 or >80 chars, case-insensitive dedup, **hard cap 100 terms** (`if len(keywords) >= 100: break`).
  - `encoding` — default `"linear16"`.
  - `sample_rate` — default `16000`; must be int, **422** if not; must be `8000 ≤ x ≤ 48000` else **422** (`chat.py:609,614-615`).
  - `channels` — default `1`; must be int, **422** if not; must be `1` or `2` else **422** (`chat.py:610,616-617`).
- **Headers:** `Authorization` (Firebase bearer, required — enforced by the route's `Depends`). `X-App-Platform` (optional, `Header(None, alias='X-App-Platform')`, `chat.py:573`) gates only the trial paywall check (see §5). **`X-App-Version` is NOT read by this handler at all** — it is not declared as a parameter of `transcribe_voice_message`. Do not rely on it reaching this endpoint.
- **Auth/quota gates before transcription:** `is_trial_paywalled(uid, x_app_platform)` → **402** `{'error': 'quota_exceeded', 'plan_type': 'basic'}` if tripped (line 586-587). Daily transcription-duration budget (`try_consume_budget`) → **429** `'Daily transcription budget exhausted'` if exhausted (line 621-624).

Windows' current `batchTranscribeParams` (`constants.ts:80-82`) sends `language, sample_rate, encoding, channels` — matches the contract exactly. It does **not** send `keywords` yet.

### Response (`response_model=VoiceMessageTranscriptionResponse`, `chat.py:93-95`)

```python
class VoiceMessageTranscriptionResponse(BaseModel):
    transcript: str
    language: Optional[str] = None
```

**That is the entire response shape.** `{"transcript": "...", "language": "..."}` (language omitted from the dict entirely, not even `null`, when not detected — `chat.py:645-648`). **There is no `stt_provider` or `stt_model` field anywhere in this endpoint's response** — confirmed by reading the full handler body and the Pydantic model; `grep -rn "stt_provider|stt_model" backend/routers/chat.py` only matches an unrelated local variable name at line 856 (`get_stt_service_for_language`, inside the *WebSocket* streaming handler, not returned to the client either).

**This directly contradicts what Mac's own client code expects.** `TranscriptionService.swift:758-764` defines `PythonTranscribeResponse` with optional `stt_provider`/`stt_model` fields and logs them (`TranscriptionService.swift:750-752`), and `BatchTranscriptionResult` carries `provider`/`model` — but since the backend never populates those keys, `JSONDecoder` just leaves them `nil` (they're `Optional`, so decoding doesn't fail) and Mac silently logs `provider=unknown model=unknown` on every real request today. **This is a pre-existing Mac/backend contract gap, not a Windows-specific concern** — the fields the brief asked about as "NEW" do not exist on the backend at all; Mac's code is speculative/dead for those two fields.

### Multipart path (mobile, not desktop) — for contrast only

Same endpoint also accepts `multipart/form-data` (files + optional `language` form field, `chat.py:650-767`) — the mobile/legacy path. Desktop PTT never uses this branch; irrelevant to Windows transport work.

### 503 / `stt_provider_configuration_error` — DOES NOT EXIST

**Grepped the entire `backend/` tree for `stt_provider_configuration_error` and `configuration_error` — zero matches anywhere**, including `routers/chat.py`, `utils/chat.py`, `utils/stt/`, and all test files. There is no 503 response of that shape from this endpoint or any STT path in this backend checkout. The only error statuses this endpoint can return are:

| Status | Trigger |
|---|---|
| 402 | `is_trial_paywalled` (desktop trial expired, `TRIAL_PAYWALL_ENABLED` gate, currently OFF by default) |
| 413 | body > 200MB (`Content-Length` pre-check or actual size) |
| 400 | empty octet-stream body |
| 422 | non-integer / out-of-range `sample_rate` or `channels` |
| 429 | daily transcription-duration budget exhausted |
| 500 | `RuntimeError` from `transcribe_pcm_bytes` (Deepgram failure) — generic `f'Transcription failed: {str(e)}'` detail, no structured error code |
| 200 | success, including "no speech detected" (`transcript: ""`, not an error) |

Mac's own `TranscriptionService.batchTranscribe` only special-cases `413` (`payloadTooLarge`) and treats every other non-200 as a generic `.invalidResponse` (`TranscriptionService.swift:733-741`) — it has no 503/stt_provider_configuration_error handling either, confirming this is not an existing contract on either platform. **Do not build 503/`stt_provider_configuration_error` handling into Windows — it would be handling a response shape the backend never sends.** If this was meant to describe planned/future work, flag it back to the brief owner; ground truth as of this checkout says it doesn't exist.

---

## 4. Deepgram-level `keywords` plumbing (for completeness)

`_parse_context_keywords` output flows: `chat.py:606,637` → `utils/chat.py:transcribe_pcm_bytes(..., keywords=context_keywords)` (`utils/chat.py:164-171`) → `prerecorded_from_bytes(..., keywords=keywords)` (`utils/chat.py:186-207`) → Deepgram's pre-recorded API `keywords` option (`utils/stt/pre_recorded.py`, not read in this pass but exercised by `TestDeepgramPrerecordedFromBytesPCM`/`TestTranscribePcmBytes` in `backend/tests/unit/test_desktop_transcribe.py`). The existing test `test_octet_stream_returns_transcript` (`test_desktop_transcribe.py:853-870`) proves the exact wire format: `?keywords=Aarav,Ansh,Aarav` → `mock_transcribe.call_args.kwargs['keywords'] == ['Aarav', 'Ansh']` (comma-split, dedup preserved, order preserved).

---

## 5. Platform recognition — `X-App-Platform: windows` — CONFIRMED RECOGNIZED (no STOP finding)

- `backend/utils/subscription.py:119`: `DESKTOP_PLATFORMS = {'macos', 'windows'}` — explicit single-source-of-truth comment: "this is the single source of truth for 'is this a desktop platform'... so a new desktop OS is wired in one place."
- `_TRIAL_PAYWALL_DESKTOP_TOKENS = DESKTOP_PLATFORMS | {"desktop"}` (line 125), used directly by `is_trial_paywalled(uid, platform)` (line 199-211), which is the exact function this endpoint calls (`chat.py:586`) with the raw `x_app_platform` header value, lowercased (line 209: `platform.lower() not in _TRIAL_PAYWALL_DESKTOP_TOKENS`).
- **`'windows'` is correctly recognized** by the only platform-gating logic this endpoint's handler invokes. No platform-variant divergence risk found here (contrast with the prior windows-plan-catalog incident noted in project memory — that was a different code path).

**However, a real (separate, smaller) gap exists on the Mac side, not the backend side:** Mac's `TranscriptionService.batchTranscribe` (the function that actually calls this endpoint for PTT) builds its `URLRequest` manually (`TranscriptionService.swift:720-727`) and **never sets `X-App-Platform`, `X-App-Version`, or `X-Device-Id-Hash`** on it — those headers are only set in the separate WebSocket-connect code path (`TranscriptionService.swift:411-415`, inside the `/v2/voice-message/transcribe-stream` connector, a different function). So on Mac, every batch PTT transcribe request goes out with `platform=None`, meaning `is_trial_paywalled` always short-circuits `False` for this call regardless of platform (harmless today only because `TRIAL_PAYWALL_ENABLED` defaults off).

**Windows is already ahead here, not behind:** `batchTranscribe` in `transport.ts:127-137` calls `omiApi.post(...)`, and `omiApi`'s shared interceptor (`apiClient.ts:104-105`) unconditionally stamps `X-App-Platform: 'windows'` (and `X-App-Version` when resolved) on every outgoing request, including this one. So Windows' batch PTT calls already carry the platform header Mac's do not. This is a case where Windows should **not** copy Mac's omission — per the port posture (deviate only where Mac is proven wrong or Windows is ahead), keep Windows' existing header behavior as-is.

---

## 6. What Windows must add to `transport.ts` / `constants.ts` (files owned by this brief)

1. **`keywords` param** — extend `batchTranscribeParams(language)` in `constants.ts` to accept an optional keyword list and append `keywords: terms.join(',')` when non-empty (mirroring Mac's query-param shape exactly: comma-separated, no URL-encoding beyond what axios does automatically for `params`). Cap defensively client-side to ~100 terms max (backend hard-caps at 100 anyway; matching Mac's stricter 40-term wire cap is a reasonable choice to keep query strings short, but not contractually required).
2. **`stt_provider`/`stt_model` — do NOT add handling for these.** The backend response never includes them (§3). Do not add speculative optional fields that mirror Mac's dead code; if/when the backend adds them, revisit. Flagging this explicitly so no one "ports" Mac's dead `stt_provider`/`stt_model` logging into Windows believing it reflects a real contract.
3. **503 `stt_provider_configuration_error` — do NOT add handling for this.** It does not exist in this backend checkout (§3). `batchErrorMessage` in `transport.ts:153-162` already has no 503 case and should stay that way unless the backend actually grows one.
4. **`X-App-Platform`/`X-App-Version` — no action needed.** Already correctly sent via the shared `omiApi` interceptor (§5); this is a case where Mac is behind, not Windows.
5. Response parsing in `batchTranscribe` (`transport.ts:127-150`) currently only reads `res.data?.transcript` — this is correct and complete given the actual response shape (`{transcript, language?}`); no change needed there beyond whatever the caller wants to do with `language` (currently discarded, matching that Windows already resolves language client-side via `getPreferences().language` sent as the request param).
