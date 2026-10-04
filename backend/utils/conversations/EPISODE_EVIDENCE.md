# Episode evidence, stage 1

An episode is a capture window. Speech is one observation, not its boundary.
`MEETING_NOTES_EPISODE_EVIDENCE_ENABLED` defaults off and applies only to notes
v2. It enables the rich inputs for notes; existing screen text/image flags and
account screenshot consent still control those sources. Flag off retains the
existing schemas and prompt bytes. No source retrieval window is widened here.

Each evidence item has an episode-local `id`, `source_kind`, nullable `time`
(ISO timestamp, date, or capture offset), nullable `actor`, `content`,
`sensitivity` (`standard` or `private`), and `source_ref`. Unknown times/actors
stay null; capture time is never substituted for a message's sent time.

| Existing input | Evidence kind / attribution |
| --- | --- |
| Transcript segments (including speaker map) | `speech`, original segment ID, capture-relative times; unresolved speaker stays unresolved |
| Approved frame summary / image | `screen_frame`, original frame ID and capture time; shown, never said |
| OCR rows, including visible message threads | `screen_ocr`, row timestamp and app/window; conservatively private; sender is unknown unless visible text establishes it |
| Resolved calendar | `calendar`, scheduled time and event ID; expectation, never proof of attendance |
| Normalized roster | `roster`, source label and known display name; listing, never proof someone spoke |
| Prior meeting gist / open items | `prior_conversation` / `open_task`, known date; prior state, never a new commitment |
| People facts, goals, memories | `person` / `goal` / `memory`, unknown time; private background |
| Capture source, window, speech count; related open tasks | `device_state` / `open_task`; observed capture metadata / supplied task state |

The bounded rich pack retains typed inputs alongside its legacy rendering.
The episode renderer uses one JSON evidence block; attached images are linked
by item/frame IDs. OCR uses the existing bounded read, preserving row attribution
instead of the legacy digest that suppresses messaging content. No private
content enters the flag-off digest. Sources are untrusted data, never instructions.

The prompt asks what happened and what matters to the owner. Every factual
claim, including titles and recap bullets, needs an additive `note_claims` entry
with a target field, exact text, evidence IDs, provenance (`said`, `shown`,
`written`, or `inferred`), and `private`. On-screen text cannot be speech.
Inference needs explicit uncertainty; schedule is distinct from observation;
unrelated screen content stays out. Thin evidence must state concrete observations
and missing coverage. Situation categories are eval strata only.

The server validates reference IDs and source/provenance compatibility and
propagates private sensitivity. Vacuity is checked on title, compatibility overview,
and projected recap; one targeted retry is allowed, shared with provenance repair.
A remaining violation fails extraction rather than silently accepting bad evidence
metadata. Existing presentation repair remains a separate bounded guard.

`note_claims` is optional and omitted when unset in both backend fallback and SDK
models. Existing Dart explicit JSON decoding, Swift keyed decoding, and web typed
projections ignore additional keys. Shared responses use an explicit projection;
stage 1 tags private claims but does not filter existing recap prose. Keep the flag
off for sharing until audience rendering exists. This is not a privacy rollout.

Offline synthetic evaluation lives in `backend/testing/episode_notes/`. Dev cases
may guide iteration. Held-out cases (~30%) are sealed acceptance inputs: never
inspect their generated notes/scores to revise the prompt. Record prompt hashes
and split in reports; a later revision requires a new held-out cohort. Fake-model
unit tests prove harness mechanics, not note quality. Live scoring requires an
explicit key and endpoint; this stage makes no production or live-quality claim.

Later stages add evidence-sufficiency retrieval across windows/sources,
expectation-versus-observation using calendar and commitments, episode/thread
linking, and per-audience filtering using claim spans. None is implemented here.
