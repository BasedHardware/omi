# Episode evidence, stage 1

An episode is a capture window. Speech is one observation, not its boundary.
`MEETING_NOTES_EPISODE_EVIDENCE_ENABLED` defaults off and applies only to notes
v2, additionally requiring sticky hashed-UID admission through
`MEETING_NOTES_EPISODE_EVIDENCE_PERCENT` (default 0, malformed values fail closed).
The boolean is the immediate kill switch. See [rollout runbook](EPISODE_ROLLOUT.md).
It enables the rich inputs for notes; existing screen text/image flags and
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
The episode renderer uses one JSON evidence block with two lists:
`expected_context` (calendar, roster, and names already stored on a screen tile)
and `observed_participation` (speech and other observed activity). A listing is
an expectation, not attendance. The renderer does not decide that someone was
absent; it only stops presenting that listing as an actor. Attached images are
linked by item/frame IDs. OCR uses the existing bounded read, preserving row attribution
instead of the legacy digest that suppresses messaging content. The flag-off
digest is unchanged. Sources are untrusted data, never instructions.

The prompt centers what happened to/for the owner, not the collected evidence.
Screen/background facts need an evidenced connection to the episode: participants,
active call surface, speech reference, owner messages, or demonstrated solo activity.
Titles/overview describe the episode; missing coverage goes in body bullets. Every factual
sentence/bullet, including titles and recap bullets, needs source-faithful wording.
When `MEETING_NOTES_EPISODE_CLAIMS_ENABLED=true` (default false), it also needs a `note_claims` entry
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
Episode presentation and claim/vacuity repair share ONE optional model call.
The active episode tier budget includes the repair, transport retries are disabled for
episode calls, and repairs are skipped for long inputs or less than 15s headroom.
Transcripts above 240k UTF-8 bytes use the existing rich prompt. Baseline behavior
is unchanged. Local sanitization always runs, including when repair is skipped.
One claim normally binds a sentence/bullet; sources or provenance changes split
it. Headings need no claims. Every factual unit still needs an anchor; repeated
ambiguous anchors are invalid. Generation omits server-authored evidence_sources,
which validation fills without model output cost. Screen selection removes repeated OCR lines/chrome on the same surface and ranks
participant/call/speech connections, with a 12k-character screen allowance and
1.2k exploratory allowance for unlinked/solo observations. Lexical rank is not
proof of relevance; the model still requires a connection. Speech is never
truncated. Compact generation keys t/p/e/v expand to the original claim schema.
Compatibility overview does not duplicate section claims. List/search projections
omit claims; detail serialization omits absent optional source fields.
Compact evidence serialization
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

The writer sees expected context and observed participation as separate lists
in that one block. Later stages add evidence-sufficiency retrieval across
windows/sources, commitment tracking, and episode/thread linking. None of
those is implemented here.

Round-9 DEV experiments preregister deterministic independent links versus a Luna
low-effort selection pass, optional claim generation, and default/high/xhigh writer
effort. `MEETING_NOTES_EPISODE_SELECTION` and `MEETING_NOTES_EPISODE_EFFORT`
are read at the call boundary; only admitted episode writers use them. Selection
passes return exact original IDs plus short connection reasons; the writer receives
only original speech and selected original evidence, never generated reasons.
Unknown IDs/invalid selection fall back to conservative independent links, and
large inputs skip the selection model. No retrieval window is widened. The actual
capture end is separate from processing time; later observations cannot establish
activity during the window. Claim-disabled notes skip claim-coverage validation,
retaining prose/presentation/vacuity checks and one bounded optional repair.
References and judges stay fixed across comparisons. Cache keys include candidate
effort/selection/claim mode. Two independently cached judgments of fixed candidates
measure judge variance; selection costs join writer tokens/latency/provider dollars.
No held-out input may guide these choices. Defaults remain subject to measured DEV
gates and external held-out acceptance; sticky rollout remains zero here.

Capture/device constraints are always retained by deterministic selection, even
without topical word overlap. The capture adapter records desktop remote-channel
mixing capability and roster-entry count (not observed speaker count); neither
establishes attendance or identity. Writer instructions require every field to
respect those constraints and keep unclear referents/intent/outcomes unresolved.
A connected evidence item can still contain unrelated clauses, which stay out.
Selector controls: `MEETING_NOTES_EPISODE_SELECTION_EFFORT` defaults low and
`MEETING_NOTES_EPISODE_SELECTION_TIMEOUT_SECONDS` defaults 30 (bounded 1–30).
Recoverable selector/repair model errors are separate from processing errors in
receipts. Source selection failure keeps the conservative evidence and continues.

Round 10 supersedes guarded C8. Base settings are C7: deterministic selection,
claims off, no effort override, optional thinking byte guard disabled (0).
The locked 2026-10-06 processing-time cost route admits C6/xhigh for at least 1500 speech
words and two admitted source kinds; thresholds are configurable. No taxonomy or
user allowlist participates. Long transcript prefixes (>240k bytes) still use rich
baseline. The same downstream contract applies to every selector/tier.

Jev uses the existing pinned SystemOne gateway/client with the `episode_evidence`
metric lane. One shared bounded state describes speech, capture times, roster and
call/device metadata. Each grouped app/window screen segment or prior/person/
memory/goal/task item gets one connection question. Oversize batches split before
transport truncation; an individually oversize item, invalid answer or timeout
fails open to deterministic selection. Speech and trusted device constraints stay.
No retrieval is added: missing catalog sources remain absent. The offline adapter
uses the identical typed request/validated answers on OpenRouter's `/systemone`,
substituting the pinned model for the gateway lane ID. DEV threshold calibration
must precede enablement; the default selector remains deterministic.

See [deadline audit](EPISODE_DEADLINES.md). Requested episode deadlines are 120s
(C7) and 180s (C6); the existing gateway's 120s ceiling clamps C6 to 115s. Only
already leased durable finalizers receive extended budgets. Synchronous request
paths retain 60s and route to C7. Baseline/legacy deadlines are unchanged. One C6
timeout/context-limit failure buys one C7 rewrite and disables further model
repair. Repairs still require 15s remaining headroom. Telemetry records requested/
effective deadline, tier, route reason, selector actually used and tier fallback.
No request effort override on C7 inherits the configured gateway effort (currently
low); explicit C6 xhigh overrides it. Offline candidate calls read that route
policy by default, with `--provider-default-effort` only for non-parity experiments.

Known BYOK models outside the supported reasoning family keep their own options,
with a fixed effort-downgrade violation. Naive capture-end timestamps use UTC,
matching the existing capture-start convention. Neither changes source text.

Calendar scheduled times and task due times are expectations, not observation
clocks; the post-capture observation filter does not discard them. They never
establish attendance or a new commitment.
