# Concrete notes preserve existing speaker authority

Chapter and episode prompts now request concrete subject-focused notes, supported quantities and
actual decisions. Unknown speakers remain someone/a participant or a neutral fact. Only the existing
`SpeakerRoleMap` / `owner_attribution` authority can authorize second-person wearer attribution.
The two episode transcript renderers reuse `transcript_for_llm.owner_safe_transcript_segments`, as
conversation notes already do; raw `is_user`, account names, calendar context and episode membership
supply no additional authority. Unknown and bystander speech remains available, with no chapter
removed for `is_user=false`. Recognition thresholds and stored segment labels do not change.

The shared deterministic output policy repairs empty/unsafe headings, filters narration about missing
capture evidence, and preserves the first real title during automatic refresh. Deferred preview and
server-minimum titles remain replaceable by the first real summary. Ordinary software-reliability
notes (for example, an action to investigate audio gaps) remain supported subject matter.

This backend policy is on by default, with no new flag, provider call, or production backfill. Existing
notes-input dedupe and compose evidence admission bound paid work. The prompt-version transition
invalidates the old contract once at the next eligible attempt. The episode feature's independent
availability switch remains authoritative; this PR does not enable it or change serving configuration.

Synthetic evidence: `tests/unit/test_summary_quality.py`, `test_summary_persistence.py`,
`test_conversation_structure_input_shape.py`, `test_episodes_incremental_live.py`, and
`test_episode_composer.py`. These cover owner-authorized versus ambiguous speech, retained chapters,
filters and counterexamples, provisional previews, and stable headlines. No account content or
identity data is added to fixtures, logs or title-change metadata. No live-model/device quality claim
or audio-custody, task-owner, billing-entitlement, or capture protocol change is made.
