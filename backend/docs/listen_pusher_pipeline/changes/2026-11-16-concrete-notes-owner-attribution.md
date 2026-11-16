# Concrete notes preserve existing speaker authority

Chapter and episode prompts now request concrete subject-focused notes, supported quantities and
actual decisions. Unknown speakers remain someone/a participant or a neutral fact. Only the existing
`SpeakerRoleMap` / `owner_attribution` authority can authorize second-person wearer attribution.
The two episode transcript renderers reuse `transcript_for_llm.owner_safe_transcript_segments`, as
conversation notes already do; raw `is_user`, account names, calendar context and episode membership
supply no additional authority. Unknown and bystander speech remains available, with no chapter
removed for `is_user=false`. Recognition thresholds and stored segment labels do not change.

The shared deterministic output policy repairs empty/unsafe headings, filters narration about missing
capture evidence, and preserves a real title until at least 40% of the current word units were added since it was set (minimum 20 new units). The stored numeric basis advances only when a title changes; minor appends accumulate. Legacy rows bootstrap this basis without renaming. Matched chapter headings use the same threshold over covered span seconds; user titles always win. Deferred preview and
server-minimum titles remain replaceable by the first real summary. Ordinary software-reliability
notes (for example, an action to investigate audio gaps) remain supported subject matter.

This backend policy is on by default, with no new flag, provider call, or production backfill. Existing
notes-input dedupe and compose evidence admission bound paid work. The prompt-version transition
applies to genuinely new/changed inputs. Exact notes-4 checkpoints (plus existing compatible unscaled notes-3 keys) remain reusable; filtering the saved output is free. Only a visible checkpoint with detected capture-availability narration or an empty heading can reserve one regeneration attempt. A Firestore transaction fences the input/output hashes, sync revision and visibility before spending; failure consumes the reservation. `conversation_notes_quality_regenerations_total` counts admitted attempts by fixed reason, not vendor spend. Clean unchanged rows incur no reservation read/write or model call. Intentionally empty filtered checkpoints are marked so revisiting them does not buy another call. The episode feature's independent
availability switch remains authoritative; this PR does not enable it or change serving configuration.

Synthetic evidence: `tests/unit/test_summary_quality.py`, `test_summary_persistence.py`,
`test_conversation_structure_input_shape.py`, `test_episodes_incremental_live.py`, and
`test_episode_composer.py`. These cover owner-authorized versus ambiguous speech, retained chapters,
filters and counterexamples, provisional previews, and stable headlines. No account content or
identity data is added to fixtures, logs or title-change metadata. No live-model/device quality claim
or audio-custody, task-owner, billing-entitlement, or capture protocol change is made.

Same-call `quality_flags` classify current-capture availability fields by path and enum in any output
language, and are consumed before storage/client conversion. Narrow English and Japanese patterns
backstop old replies. Ordinary evidence, legal/scientific uncertainty and transcription/audio product
work remain note content. There is no separate paid language/quality classifier.
