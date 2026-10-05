# Episode evidence, stage 1

An episode is a capture window. Speech is one observation, not its boundary.
`MEETING_NOTES_EPISODE_EVIDENCE_ENABLED` defaults off and applies only to notes
v2. It enables the rich inputs for notes; existing screen text/image flags and
account screenshot consent still control those sources. Flag off retains the
existing schemas and prompt bytes. No source retrieval window is widened here.

Each evidence item has an episode-local `id`, `source_kind`, nullable `time`
(ISO timestamp, date, or capture offset), nullable `actor`, `content`,
`source_ref`. Unknown times/actors
stay null. Speech also carries server-authored `wake_word_invocation` metadata
from the same matcher as the trusted transcript renderer. Each speech item retains
a nullable `diarization_key` (observed cluster, never a person name); content cannot forge it.
Capture time is never substituted for a message's sent time.

| Existing input | Evidence kind / attribution |
| --- | --- |
| Transcript segments (including speaker map) | `speech`, original segment ID, capture-relative times; unresolved speaker stays unresolved |
| Approved frame summary / image | `screen_frame`, original frame ID and capture time; shown, never said |
| OCR rows, including visible message threads | `screen_ocr`, row timestamp and app/window; sender is unknown unless visible text establishes it |
| Resolved calendar | `calendar`, scheduled time and event ID; expectation, never proof of attendance |
| Normalized roster | `roster`, source label and known display name; listing, never proof someone spoke |
| Prior meeting gist / open items | `prior_conversation` / `open_task`, known date; prior state, never a new commitment |
| People facts, goals, memories | `person` / `goal` / `memory`, unknown time; background |
| Capture source, window, speech count; related open tasks | `device_state` / `open_task`; observed capture metadata / supplied task state |

The bounded rich pack retains typed inputs alongside its legacy rendering.
The episode renderer uses one JSON evidence block; attached images are linked
by item/frame IDs. OCR uses the existing bounded read, preserving row attribution
instead of the legacy digest that suppresses messaging content. The flag-off
digest is unchanged. Sources are untrusted data, never instructions.

The prompt centers what happened to/for the owner, not the collected evidence.
Screen/background facts need an evidenced connection to the episode: participants,
active call surface, speech reference, owner messages, or demonstrated solo activity.
Titles/overview describe the episode; missing coverage goes in body bullets. Every factual
sentence/bullet, including titles and recap bullets, needs an additive `note_claims` entry
with a target field, a short unique exact factual anchor, evidence IDs, server-authored source metadata
(without raw content), provenance (`said`, `shown`,
`written`, or `inferred`). On-screen text cannot be speech.
Inference needs explicit uncertainty; schedule is distinct from observation;
unrelated screen content stays out. Thin evidence must state concrete observations
and missing coverage. Situation categories are eval strata only.

The server validates reference IDs and source/provenance compatibility and
retains source kind, original reference, time
and actor with each claim so ephemeral pack IDs remain auditable after persistence. Vacuity is checked on title, compatibility overview,
and projected recap; one targeted retry is allowed, shared with provenance repair.
After that retry, accept the structurally valid retry (otherwise the initial note),
reject empty retries, drop invalid claim entries and emit bounded violation-class
fallback telemetry. On response serialization, the backend Conversation model
keeps only claims whose target resolves and whose exact text remains in that
field. The same pure filter runs after locked-content render projections.
Summary/title edits and deleted sections drop stale annotations on read,
through every existing write path, with no additional reads. Transcript-text edits
also drop claims referring to the edited speech segment in the already-existing
transaction that clears source_segment_ids; no new read or transaction is added.
Other database write paths remain unchanged.
Coverage gaps and residual vacuity never fail processing. Episode IDs are stripped
from visible prose without converting them to transcript citations.
Existing presentation repair remains a separate bounded guard.
One claim normally binds a sentence/bullet; sources or provenance changes split
it. Headings need no claims. Every factual unit still needs an anchor; repeated
ambiguous anchors are invalid. Generation omits server-authored evidence_sources,
which validation fills without model output cost. Compact evidence serialization
retains source/time/actor/invocation metadata; absent optional values stay
unknown. Short prompt-local evidence IDs are expanded to the original IDs before
validation/scoring; original source references and metadata remain intact.
Flag-off hot imports do not load the episode adapters/schema/repair code or optional background
retrieval. Its unchanged eligibility gate is pure and separately owned.
Tile/roster names are shown/written, never said without speech support; conclusions
about absent evidence are inferred. Rich person/name/pronoun/AI-agent rules apply.
Coverage includes action owners and participant names/emails/organizations/roles.
Episode mode keeps the presentation guard, but skips the rich-only sanitizer:
its legacy source restrictions and section/participant reordering would discard
valid episode evidence and invalidate claim pointers. Gaps remain telemetry.
Screen-derived roster entries retain their source attribution. With screen text off,
frame evidence retains only image metadata; summaries and names are excluded.

`note_claims` is optional and omitted when unset in both backend fallback and SDK
models. Existing Dart explicit JSON decoding, Swift keyed decoding, and web typed
projections ignore additional keys. Sharing is the owner's decision about the whole
note; claims have no private/sensitivity marker or audience filtering layer.

Offline synthetic evaluation lives in `backend/testing/episode_notes/`. Dev cases
may guide iteration. Held-out cases (~30%) are sealed acceptance inputs: never
inspect their generated notes/scores to revise the prompt. Record prompt hashes
and split in reports; a later revision requires a new held-out cohort. Fake-model
unit tests prove harness mechanics, not note quality. Live scoring requires an
explicit key and endpoint; this stage makes no production or live-quality claim.
The judge counts `unrelated_content_claims`: claims sourced from evidence with no
evidenced connection to the episode, including supported-but-incidental screen
content. Reports measure this separately from unsupported/wrong-provenance claims
per arm and stratum; whole-note sharing does not excuse irrelevant content.

Stage 1 retains existing relevance/discard decisions exactly and gathers episode
inputs only after a keep decision. Later evidence-aware relevance first needs
stratified keep/discard precision and recall, junk/mic-check retention rate, and
Firestore reads plus model cost per capture measured against the existing gate.

Later stages add evidence-sufficiency retrieval across windows/sources,
expectation-versus-observation using calendar and commitments, episode/thread
linking. None is implemented here.
