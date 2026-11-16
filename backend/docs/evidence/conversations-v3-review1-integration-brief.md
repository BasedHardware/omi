# Scope: preserve v3 repairs across the advanced main target

Read-only scope task, not implementation. Candidate: 47e0450a547 on
lane/conversations-v3. Original base 92b697098eb6ff200165cf005577c916aeab189f. Current main 1ed16cae960589255dfc70f63db31e95cc587a4c.

The user gave a six-review repair packet. Backend repairs are committed and
focused tests pass. The metadata preflight now cannot simulate integrating
this candidate into current origin/main: content conflicts in exactly:
backend/models/conversation.py, backend/utils/conversations/process_conversation.py,
and config/feature-flags.yaml. Main advanced during verification, including
Q12 summary/title stability, original speaker evidence and AI profile work.

Recommend the smallest safe strategy to make the feature apply cleanly to that
pinned target, while preserving its semantics and the owners' new behavior.
Identify precise conflicting insertions and verification needed. Consider
whether mechanical relocation of feature additions can preserve an automatic
integration, versus carrying dependency-closed upstream changes. Do not assume
that wholesale copying current main files is safe. No edits, commits or commands
that mutate Git history/state; report findings only with file/line evidence.

Constraints:
- All final edits belong to the primary agent in the user-provided worktree.
- No history rewrite, rebase, push, PR creation/merge, deploy or live config.
- No production access, credentials, private user data or model calls to Omi.
- Do not read/search any other working tree or any upstream-keep-clean/ directory.
  The panel's own isolated checkout is allowed. Git objects for pinned refs are
  allowed; use git show/diff for upstream instead of another working tree.
- No app UI edits (app/lib/pages, providers, widgets). Generated wire output only.
- Q12-AU owns sync duplicate merge; Q12-AV owns summary prompts and title stability.
  Preserve their code; do not invent a new prompt or rewrite their sync merge.
- V3 short extraction is 20–299 words after existing content/quiet minima;
  foreground summary is Standard; background summary Flex-first/Standard fallback.
  Recording processing remains no-op; v3 title_locked must win across rebuilds.

This is a bounded integration scope, not another whole-feature review. Existing
review decisions/tests are recorded in conversations-v3-review1-2026-11-16.md.

Pinned upstream model/processing diff:

```diff
diff --git a/backend/models/conversation.py b/backend/models/conversation.py
index 532f5ad8ee5..40eb76dddea 100644
--- a/backend/models/conversation.py
+++ b/backend/models/conversation.py
@@ -432,6 +432,21 @@ class ConversationSpeakers(BaseModel):
     status: Literal['resolved', 'capture', 'unavailable']
     version: int = 1
     participant_speaker_ids: List[int] = []
+    input_membership_sha256: SkipJsonSchema[Optional[str]] = Field(default=None, exclude=True)
+
+    @model_serializer(mode='wrap')
+    def _serialize_membership(self, handler, info):
+        data = handler(self)
+        excluded = info.exclude if isinstance(info.exclude, (dict, set, frozenset)) else ()
+        included = info.include
+        if (
+            info.mode != 'json'
+            and self.input_membership_sha256 is not None
+            and 'input_membership_sha256' not in excluded
+            and (included is None or 'input_membership_sha256' in included)
+        ):
+            data['input_membership_sha256'] = self.input_membership_sha256
+        return data


 class CaptureEvidenceMetadata(BaseModel):
@@ -464,6 +479,8 @@ class RecordAudioPartial(BaseModel):


 class Conversation(BaseModel):
+    title_content_units: float = Field(default=0, exclude=True)
+    notes_quality_filter_input_hash: Optional[str] = Field(default=None, exclude=True)
     notes_llm_input_hash: Optional[str] = Field(default=None, exclude=True)
     notes_llm_output_hash: Optional[str] = Field(default=None, exclude=True)
     l1_llm_input_hash: Optional[str] = Field(default=None, exclude=True)
diff --git a/backend/utils/conversations/process_conversation.py b/backend/utils/conversations/process_conversation.py
index eabae58f3f2..30289f5f19a 100644
--- a/backend/utils/conversations/process_conversation.py
+++ b/backend/utils/conversations/process_conversation.py
@@ -97,6 +97,15 @@ from utils.conversations.deterministic_minimum import (
     deterministic_minimum_title,
 )
 from utils.conversations.duration import conversation_duration_seconds
+from utils.conversations.home_titles import title_for_stability
+from utils.summary_quality import (
+    clean_structured,
+    stable_title,
+    valid_title,
+    title_or_fallback,
+    content_units,
+    title_basis,
+)
 from utils.conversations.duplicate_capture import link_duplicate_captures
 from utils.conversations.sync_hold_completion import complete_explicit, defer_held_budget_denial
 from utils.conversations.merge_before_processing import before_notes, ConversationAbsorbed
@@ -196,12 +205,13 @@ from utils.managed_compute import (
     managed_compute_decision_for as _managed_compute_decision_for,
 )
 from models.other import Person
-from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.
+from models.structured import Section, Structured  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.
 from utils.notifications import send_important_conversation_message
 from models.task import Task, TaskStatus, TaskAction, TaskActionProvider
 from models.notification_message import NotificationMessage
 from utils.default_summary_template import DEFAULT_SUMMARY_APP_ID, default_summary_app
 from utils.apps import get_available_app_model_by_id, get_available_apps, update_persona_prompt
+from utils import ai_profile_refresh
 from utils.executors import llm_executor, postprocess_executor, submit_with_context
 from utils.llm.conversation_processing import (
     get_app_result,
@@ -725,6 +735,33 @@ def _get_conversation_obj(
     relevance_discarded: Optional[bool] = None,
     user_kept: bool = False,
 ) -> Conversation:
+    if relevance_discarded is False:
+        cleaned = clean_structured(structured.model_dump())
+        if not valid_title(structured.title):
+            cleaned['title'] = title_or_fallback(
+                deterministic_minimum_title(
+                    conversation, tz_name_provider=lambda: notification_db.get_user_time_zone(uid)
+                )
+            )
+        old_title = title_for_stability(conversation)
+        cleaned['title'], title_reason = stable_title(
+            old_title,
+            cleaned['title'],
+            previous_units=getattr(conversation, 'title_content_units', 0),
+            current_units=content_units(getattr(conversation, 'transcript_segments', [])),
+        )
+        if isinstance(conversation, Conversation):
+            conversation.title_content_units = title_basis(
+                conversation.title_content_units, content_units(conversation.transcript_segments), title_reason
+            )
+        if str(getattr(conversation, 'user_title', '') or '').strip():
+            cleaned['title'] = conversation.user_title
+        # Preserve private notes identity carried on the model instance.
+        for key in ('title', 'overview', 'gist'):
+            if key in cleaned:
+                setattr(structured, key, cleaned[key])
+        if 'sections' in cleaned:
+            structured.sections = [Section.model_validate(section) for section in cleaned['sections']]
     structured = finish_home_salience(uid, structured, conversation, user_kept=user_kept)
     if relevance_discarded is False and not structured.title.strip():
         # Give kept partial outputs a deterministic title; explicit discards keep theirs empty.
@@ -2637,6 +2674,14 @@ def process_conversation(
         )

     def _observe_owner_recognition_completion(completed: Conversation) -> None:
+        # Keep current-revision observation inside the telemetry boundary:
+        # importing or emitting optional metrics must not interrupt persistence.
+        try:
+            from database.owner_identity_availability import observe_safely
+
+            observe_safely(uid, completed.id)
+        except Exception:
+            logger.warning('event=owner_identity_availability outcome=observation_unavailable')
         # One observation per conversation, on every successful persist. The
         # completed stores return through report_persistence, so a new
         # early return that reports a
@@ -2924,6 +2969,8 @@ def process_conversation(
     if NOTES_OUTPUT_HASH in llm_hashes:
         llm_hashes[NOTES_OUTPUT_HASH] = output_fingerprint(structured)
     payload.update(llm_hashes)
+    if not conversation.discarded:
+        payload['content_word_units'] = content_units(conversation.transcript_segments)
     if 'extractions' in open_loop_sink:
         # Server-only derived field, deliberately outside the client wire
         # model, like RELEVANCE_DECISION_FIELD below. None is a fresh parse
@@ -3151,6 +3198,8 @@ def process_conversation(
                 submit_with_context(postprocess_executor, _save_action_items, uid, conversation, people, trigger)
             if not (template_only or app_failed):
                 submit_with_context(postprocess_executor, update_goal_progress, uid, conversation)
+            # Daily backend-owned AI profile refresh: no-op unless stale, bounded per process.
+            ai_profile_refresh.schedule_refresh(uid)
         # Recovery preserves admitted audio ids instead of rebuilding old chunks.
         capture_audio = not is_recovery_trigger(trigger)
         if not is_reprocess and conversation.private_cloud_sync_enabled and capture_audio:

```

The flag conflict is at the flags-list insertion point. Read the exact top
hunk from the pinned Git object if available; registry order has no semantics.
