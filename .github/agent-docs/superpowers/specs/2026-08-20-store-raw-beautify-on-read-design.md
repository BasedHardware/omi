# Store Raw Segments, Beautify on Read — Design Evaluation

Date: 2026-08-20
Status: **evaluation only** (no migration in this change)
Source comment: `backend/utils/conversations/postprocess_conversation.py` (open design question on store-raw / beautify-on-read)
Related: `backend/models/transcript_segment.py` (`combine_segments`), `backend/utils/stt/pre_recorded.py` (`postprocess_words` / `_merge_segments`)

## Problem statement

An open design question in the FAL postprocess pipeline asks whether Omi should **store non-beautified (raw) transcript segments and beautify on read**, instead of persisting the already-merged list written today.

That change would touch the identity, encryption, live WebSocket delta, edit, LLM, sync, and search contracts that treat `transcript_segments` as a single canonical list. This note evaluates current behavior, tradeoffs, migration risk, and a recommended follow-up. **It does not authorize or schedule the migration.**

## Current behavior (as of `main`)

### What “beautify” means here

There is no function named `beautify`. In this codebase that design question maps to **write-path segment merging and cleanup**:

| Path | Merger | When it runs | Result stored? |
|---|---|---|---|
| Live `/v4/listen` | `TranscriptSegment.combine_segments` | On every STT batch before Firestore write | Yes — full combined list in `transcript_segments` |
| Pre-recorded / FAL postprocess | `postprocess_words` → `_merge_segments` (+ capitalize) | After batch retranscription | Yes — on FAL success, **replaces** canonical `transcript_segments` |
| Offline sync append | Dedupe / append helpers (not `combine_segments`) | Sync pipeline | Yes — appended into stored list |
| Conversation merge | Time-offset append | Merge API | Yes |

`combine_segments` (`backend/models/transcript_segment.py`) does more than join text:

- Same-speaker merge (gap &lt; 3s, short or incomplete prior text)
- Lowercase continuation merges
- Cross-speaker incomplete-sentence repair (moves / steals sentence fragments)
- Provider barrier (`stt_provider` mismatch blocks merge)
- Punctuation spacing normalize
- Can **drop segment ids** (`removed_ids`) when a prior tail is emptied — live clients receive `SegmentsDeletedEvent`

Pre-recorded `_merge_segments` uses a different policy (same speaker, gap &lt; 30s, max segment span 30s, word-level slice of long entries). Live and FAL “beautify” are **not the same algorithm**.

### Persistence shape

Canonical field: `users/{uid}/conversations/{id}.transcript_segments`

1. JSON list of segment dicts
2. zlib-compressed (`transcript_segments_compressed=True`)
3. AES-encrypted when data protection is enhanced

Reads decrypt/decompress and return the **last written list**. There is no read-path merge.

Postprocess also stores provider A/B copies via `store_model_segments_result` under plaintext subcollections (`…/{model_name}/{segment_id}`), including streaming model name and `fal_whisperx`. Those are comparison artifacts, not the live wire contract.

### Consumers that assume the stored list is display-ready

- Live WS: clients apply server-combined `updated` segments + `segments_deleted`
- Detail/list APIs: return stored segments after decrypt
- Speaker assignment / segment text edit: mutate by `segment.id` or index, rewrite whole array
- LLM summarization / action items: `segments_as_string` / segment-id provenance over stored list
- Transcript chunk indexing, MCP transcript search, conversation merge, fair-use/duration geometry

**No production read path calls `combine_segments` today.**

## Proposed alternative (the open design question)

**Store raw** STT atoms (or less-merged segments) as the durable record; **apply beautify when serving** reads (API, LLM, clients).

Implied goals usually attached to that idea:

1. Re-run improved merge rules without re-transcribing audio
2. Keep finer timing / word boundaries for diarization, search, or reprocess
3. Avoid permanently baking a lossy merge into encrypted storage

## Tradeoffs

### Keep write-time beautify (current)

**Pros**

- Single list: storage, API, live deltas, edits, and LLM all agree on ids and text
- Merge cost paid once per write, not on every read / list hydrate
- Live clients already implement the combined-delta + delete protocol
- Matches released OpenAPI / app-client expectation that `transcript_segments` is the displayable transcript

**Cons**

- Improving `combine_segments` does not retroactively reshape historical conversations
- FAL postprocess overwrites the streaming-beautified list; streaming survives only in `model_segments` subcollections
- Lossy merges (id drops, sentence moves) are irreversible without audio reprocess

### Store raw + beautify on read

**Pros**

- Raw atoms remain available for re-merge, analytics, and future diarization
- Beautify policy can evolve without a full audio reprocess
- Clearer separation of “STT truth” vs “UI presentation”

**Cons**

- Segment **identity** becomes a derived view: merges invent/drop ids. Speaker assign, translation-by-id, action-item `[segment:…]` labels, and live `SegmentsDeletedEvent` all break unless redesigned
- Live WS would either push raw (UI must merge) or push beautified deltas that no longer match stored ids
- User edits must target raw atoms or a stable edit layer; re-beautify after edit is otherwise non-deterministic
- Dual storage (raw + cached beautified) doubles compressed/encrypted payload and complicates list hydration
- Two merge algorithms (live vs FAL) must be unified or versioned before read-path beautify is meaningful
- Sync / merge / chunk indexing currently assume stored granularity

## Migration risk (why not “just flip it”)

| Risk area | Why it hurts |
|---|---|
| Segment identity | Stable `id` is a product contract across live WS, edits, translations, action items |
| Live delta protocol | Clients already apply server-combined updates; double-beautify or raw push desyncs UI |
| FAL replacement | Success path replaces canonical list; raw vs beautified roles for streaming vs FAL must be defined first |
| Positional legacy | Desktop `#index:N` style targets depend on stored segment count/order |
| Search / vectors | Transcript chunks window by segment count; granularity change implies reindex |
| Encryption / size | Dual fields or larger raw lists increase Firestore payload and decrypt cost on list paths |
| Client OpenAPI | Released app-client contract treats `transcript_segments` as the displayable list |

A blind migration that only “beautifies on GET” while leaving live write + edit paths unchanged would create **three incompatible views** of the same conversation (raw store, live combined cache, read-time merge).

## Recommendation

**Do not implement store-raw / beautify-on-read as a wholesale flip.** Keep write-time beautify as the canonical product list.

If the underlying need is reprocessability or finer STT atoms, prefer an **additive** path:

1. **Keep** `transcript_segments` as today’s client-facing, write-beautified list (no wire break).
2. **Optionally add** a raw / high-granularity store (new field or existing `model_segments`-style subcollection) written only on paths that already have word-level or pre-merge data (postprocess, maybe live buffer snapshots).
3. **Gate** any consumer of raw data behind an explicit API or internal tool; do not change GET `/v1/conversations/{id}` semantics.
4. **Unify or version** merge policy (`combine_segments` vs `_merge_segments`) before investing in read-path presentation.
5. Only after identity, edit, and live-delta contracts are specified for dual layers, reconsider whether a read adapter should *optionally* re-beautify from raw for internal reprocess — not as the default client path.

## Recommended follow-up (scoped slices)

Ordered so each slice is independently verifiable; none of these is started by this doc:

1. **Clarify the open design question in code comments** (or remove it) once a decision is recorded — point at this note.
2. **Inventory** which writers still have access to pre-`combine_segments` atoms (live buffer vs only the combined list). If raw is already discarded in memory, “store raw” needs a live-pipeline change first.
3. **Decide ownership of merge policy**: one shared merger with version tag vs keep live/FAL separate and document why.
4. If raw retention is justified: design `transcript_segments_raw` (or subcollection) write + retention/encryption parity + size budget — **additive**, dual-write, no read flip.
5. Only then: internal “re-beautify from raw” tool for support/reprocess, with golden fixtures comparing old stored list vs regenerated view.
6. Defer any public API / client change until (4)–(5) prove value without breaking edits or live sync.

## Out of scope

- Implementing dual storage or read-path merge
- Changing FAL postprocess success/failure thresholds
- Replacing FAL with groq+pyannote (adjacent open question in the same file)
- Client UI changes

## Decision

**Status quo stands.** Store-raw / beautify-on-read remains a deferred architectural option with high blast radius; pursue only via the additive follow-ups above, not as an in-place migration of `transcript_segments`.
