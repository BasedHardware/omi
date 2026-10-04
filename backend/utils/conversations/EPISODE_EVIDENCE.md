# Episode evidence, stage 1

An episode is a capture window. Speech is one observation, not its boundary.
`MEETING_NOTES_EPISODE_EVIDENCE_ENABLED` defaults off and applies only to notes
v2. It enables the rich inputs for notes; existing screen text/image flags and
account screenshot consent still control those sources. Flag off retains the
existing schemas and prompt bytes. No source retrieval window is widened here.

Each evidence item has an episode-local `id`, `source_kind`, nullable `time`
(ISO timestamp, date, or capture offset), nullable `actor`, `content`,
`sensitivity` (`standard` or `private`), and `source_ref`. Unknown times/actors
stay null. Speech also carries server-authored `wake_word_invocation` metadata
from the same matcher as the trusted transcript renderer. Each speech item retains
a nullable `diarization_key` (observed cluster, never a person name); content cannot forge it.
Capture time is never substituted for a message's sent time.

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
with a target field, exact text, evidence IDs, server-authored source metadata
(without raw content), provenance (`said`, `shown`,
`written`, or `inferred`), and `private`. On-screen text cannot be speech.
Inference needs explicit uncertainty; schedule is distinct from observation;
unrelated screen content stays out. Thin evidence must state concrete observations
and missing coverage. Situation categories are eval strata only.

The server validates reference IDs and source/provenance compatibility and
propagates private sensitivity. It stores source kind, original reference, time
and actor with each claim so ephemeral pack IDs remain auditable after persistence. Vacuity is checked on title, compatibility overview,
and projected recap; one targeted retry is allowed, shared with provenance repair.
After that retry, accept the structurally valid retry (otherwise the initial note),
reject empty retries, drop invalid claim entries and emit bounded violation-class
fallback telemetry. On response serialization, the backend Conversation model
keeps only claims whose target resolves and whose exact text remains in that
field. The same pure filter runs after locked-content render projections.
Edits and deleted sections therefore drop stale annotations on read, through
every existing write path, with no database changes or additional reads.
Coverage gaps and residual vacuity never fail processing. Episode IDs are stripped
from visible prose without converting them to transcript citations.
Existing presentation repair remains a separate bounded guard.
Coverage includes action owners and participant names/emails/organizations/roles.
Episode mode keeps the presentation guard, but skips the rich-only sanitizer:
its legacy source restrictions and section/participant reordering would discard
valid episode evidence and invalidate claim pointers. Gaps remain telemetry.
Screen-derived roster entries inherit private sensitivity. With screen text off,
frame evidence retains only image metadata; summaries and names are excluded.

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

Stage 1 retains existing relevance/discard decisions exactly and gathers episode
inputs only after a keep decision. Later evidence-aware relevance first needs
stratified keep/discard precision and recall, junk/mic-check retention rate, and
Firestore reads plus model cost per capture measured against the existing gate.

Later stages add evidence-sufficiency retrieval across windows/sources,
expectation-versus-observation using calendar and commitments, episode/thread
linking, and per-audience filtering using claim spans. None is implemented here.
