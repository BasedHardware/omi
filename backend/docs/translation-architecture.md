# ADR-001: Full-Text vs Delta Translation in Streaming Coordinator

## Status

**Accepted** (2026-03-31, implicit — original implementation)  
**Superseded By:** DD-008 improvements (PR #28, 2026-06-14)

## Context

Real-time translation during speech-to-text (STT) produces evolving text. As Deepgram streams transcript segments, each segment's text grows incrementally:

```
"Hola" → "Hola como" → "Hola como estas" → "Hola como estas bien"
```

The `TranslationCoordinator` must decide what to send to the Google Translate V3 API on each update cycle.

## Decision

Send **full segment text** (not just the delta/new portion) to the batch translator.

### Rationale

1. **Translation quality**: Google Translate V3's NMT model produces better output for complete sentences than for fragments. Full context enables:
   - Correct gender agreement (`"Las estudiantes son inteligentes"` → `"The students are intelligent"`, not `"intelligent"` losing feminine)
   - Idiom recognition (`"Estoy de acuerdo"` → `"I agree"`, not `"acuerdo"` → `"agreement"`)
   - Proper word ordering in language pairs with different SVO structures

2. **Assembly simplicity**: The `assembled_translation` stored in `SegmentState` IS the final persisted result — it must be high quality since it's written to Firestore and displayed to users. No stitching logic needed.

3. **Stability gates filter most fragments**: Text only reaches the TRANSLATE gate when it has sentence-ending punctuation, a speaker switch, >700ms silence, STT `is_final` signal, or ≥12 tokens open for ≥3 seconds. By the time text reaches Google, it's usually a complete clause.

## Consequences

### Positive

| Aspect | Impact |
|--------|--------|
| Translation quality | High — full NMT context for all persisted results |
| Code simplicity | Single-phase architecture, no delta-stitching logic |
| Debuggability | Each translation is self-contained; easy to inspect |
| Cache correctness | Full-text cache entries are always valid as-is |

### Negative

| Aspect | Impact | Dollar Cost |
|--------|--------|-------------|
| Redundant API calls | Evolving text generates unique MD5 cache keys at every step | ~$1,700–2,350/mo avoidable |
| Cache hit rate depression | Identical sentences across different segments don't dedup | Current: ~9% effective hit rate |
| Firestore write amplification | Each intermediate translation overwrites previous one | ~5x writes per stabilized segment |
| Character throughput | 284M chars/mo vs ~120–170M chars/mo potential | $4,282/mo vs ~$1,900–2,500/mo target |

## Alternatives Considered

### Alternative A: Delta Text + Stitching
Send only `new_text` (the uncommitted portion) to the API. Stitch onto previous `assembled_translation`.

**Rejected initially** because:
- Fragment quality risk (see Rationale #1 above)
- Complex stitching logic needed for STT backtracking
- Would need to detect when STT revises earlier words

**Re-evaluated in DD-008** as Phase 2 (future work) with streaming best-effort + finalization quality guarantee.

### Alternative B: Two-Phase Architecture (Streaming + Finalization)
- **Streaming phase**: Send deltas for real-time UX (best-effort quality)
- **Finalization phase**: On stability signal, send full text split into sentences with per-sentence caching

**Selected as future direction** (DD-008 Phase 2). Not implemented yet because it requires significant architectural changes and STT backtracking handling.

### Alternative C: Sentence-Level Dedup Only (CHOSEN — This PR)
Keep sending full text, but split into sentences before cache lookup. Preserves full-sentence translation quality while eliminating redundant translations of identical sentences across segments/users.

**Implemented in PR #28** alongside merge-aware Redis lookup.

## This PR's Changes (DD-008 Phase 1 + 3)

| Change | File | What | Savings |
|--------|------|------|---------|
| Sentence-level dedup | `translation.py:translate_units_batch()` | Split texts → per-sentence cache check → reassemble | $1,070–$1,500/mo |
| Merge-aware Redis lookup | `translation_coordinator.py:199-214` | On prefix reset, check Redis before re-translating | $430–640/mo |
| Design-decision comments | `translation_coordinator.py` | Document why full text is sent, trade-offs, future path | $0 (documentation) |

## References

- DD-008 deep dive: `deep-dives/DD-008-translate-dedup-gap.md`
- DD-008 design review: `deep-dives/DD-008-design-review.md`
- Original implementation: commit `fd25ede51` (PR #6155/#6178 by Thinh, 2026-03-31)
- Google Cloud Translate V3 API: https://cloud.google.com/translate/docs/basic/translating-text
