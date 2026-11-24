"""Read-only serving prompt for the text-only ordinary sync worker."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from config.refactor_modes import serving_for
from config.jev_decisions import relevance_arm, relevance_experiment_active
from database import notifications as notification_db, redis_db, users as users_db
from database.action_item_dedup import may_have_recent_dedup_candidates
from database.conversations import get_conversation_photos
from models.conversation import Conversation
from models.other import Person
from utils.conversations.meeting_notes_wiring import confirmed_corrections_context
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import decide_relevance
from utils.conversations.relevance_io import adjacent_conversation, occasion_retention, short_clip_relevance
from utils.conversations.duration import conversation_duration_seconds
from utils.conversations.wake_word import has_structural_wake_word_marker
from utils.llm.usage_tracker import Features, track_usage
from utils.llm.conversation_processing import should_discard_conversation
from utils.conversations.transcript_for_llm import conversation_transcripts_for_llm
from utils.llm.conversation_processing import one_shot_notes_messages
from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix
from utils.llm.known_spellings import conversation_known_spellings, spelling_context_run
from utils.llm.output_language import resolve_output_language
from utils.llm.notes_short_clip import quiet_minimum
from utils.llm.notes_short_clip_policy import selected_summary_app
from utils.release_probe import is_release_probe_uid


@spelling_context_run
def notes_request(
    client: Any,
    uid: str,
    conversation: Conversation,
    *,
    user_kept: bool,
    run_relevance_model: Callable | None = None,
) -> dict[str, Any] | None:
    source = getattr(conversation.source, 'value', conversation.source)
    external = conversation.external_data or {}
    if (
        source not in ('omi', 'phone')
        or conversation.is_call
        or conversation.calendar_event
        or conversation.calendar_event_id
        or external.get('calendar_meeting_context')
        or external.get('merge_metadata')
        or conversation.photos
        or get_conversation_photos(uid, conversation.id, firestore_client=client)
    ):
        return None
    texts = [segment.text for segment in conversation.transcript_segments]
    if not any(text.strip() for text in texts) and not user_kept and not is_release_probe_uid(uid):
        from utils.conversations.process_conversation import _calendar_overlap_retains_conversation

        decision = decide_relevance(
            trigger=ProcessingTrigger.SYNC_UPDATE,
            texts=texts,
            speech_seconds=None,
            has_photos=False,
            user_kept=False,
            exempt=False,
            trusted_wake_word=False,
            model_discards=None,
            calendar_retains=lambda: _calendar_overlap_retains_conversation(
                uid, conversation.started_at, conversation.finished_at
            ),
        )
        if decision.discard and decision.reason == 'empty_transcript':
            return {'minimum': _minimum_result('', decision)}
    tz = notification_db.get_user_time_zone(uid) or ''
    selected_app = selected_summary_app(uid, False, redis_db.get_user_preferred_app)
    minimum = quiet_minimum(uid, conversation, tz=tz, user_kept=user_kept, summary_app_selected=selected_app)
    if minimum is not None:
        from utils.conversations.process_conversation import _calendar_overlap_retains_conversation

        decision = short_clip_relevance(
            uid, conversation, ProcessingTrigger.SYNC_UPDATE, _calendar_overlap_retains_conversation
        )
        return {'minimum': _minimum_result(minimum.title, decision)}

    # The normal path can buy an embedding to find related tasks. Leave that
    # work to a separately journaled operation when the empty probe is inconclusive.
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    if may_have_recent_dedup_candidates(uid, cutoff, {conversation.id}, firestore_client=client):
        return None

    person_ids = conversation.get_person_ids()
    people = Person.deserialize_many_safe(users_db.get_people_by_ids(uid, person_ids)) if person_ids else []
    plain_transcript, transcript, speaker_map = conversation_transcripts_for_llm(uid, conversation, people)
    language = conversation.language or 'en'
    prefix = build_conversation_prompt_prefix(
        uid=uid,
        conversation_id=conversation.id,
        transcript=transcript,
        started_at=conversation.started_at,
        timezone_name=tz,
        language_code=language,
        speaker_map=speaker_map,
        transcript_segment_ids=[segment.id for segment in conversation.transcript_segments],
        known_spellings=conversation_known_spellings(uid),
    )
    messages = one_shot_notes_messages(
        prefix,
        uid,
        started_at=conversation.started_at,
        language_code=language,
        output_language_code=resolve_output_language(uid, language, conversation.transcript_segments),
        tz=tz,
        task_intelligence_capture=False,
        existing_action_items=[],
        meeting_context=confirmed_corrections_context(conversation) or None,
    )
    if messages is None:
        return None
    relevance = None
    if run_relevance_model is not None:
        relevance = _assess_relevance(uid, conversation, user_kept, plain_transcript, transcript, run_relevance_model)
        if relevance.discard:
            return {'minimum': _minimum_result('', relevance)}
    plan: dict[str, Any] = {'messages': messages, 'rich_sections': serving_for('NOTES_PACKET_V2_MODE', uid)}
    exempt = is_release_probe_uid(uid)
    if relevance is not None:
        plan['relevance'] = relevance.as_record()
    elif user_kept or exempt:
        # The serving policy decides these tiers before consulting the transcript,
        # neighboring conversations, or the relevance provider.
        decision = decide_relevance(
            trigger=ProcessingTrigger.SYNC_UPDATE,
            texts=(),
            speech_seconds=None,
            has_photos=False,
            user_kept=user_kept,
            exempt=exempt,
            trusted_wake_word=False,
            model_discards=None,
            calendar_retains=lambda: False,
        )
        plan['relevance'] = decision.as_record()
    return plan


def _minimum_result(title, decision):
    return {
        'title': title,
        'discarded': decision.discard,
        'reason': decision.reason,
        'decided_by': decision.decided_by,
        'rules_version': decision.as_record()['rules_version'],
    }


def _assess_relevance(uid, conversation, user_kept, plain, transcript, run_model):
    from utils.conversations.process_conversation import _calendar_overlap_retains_conversation
    from utils.conversations.relevance_jev import jev_discard_probability, jev_tier_applies, relevance_transcript

    segments = conversation.transcript_segments
    has_wake_word = has_structural_wake_word_marker(transcript)
    arm = relevance_arm(conversation.id)
    jev_transcript = relevance_transcript(segments)
    jev_discard = None
    if arm == 'jev' and not has_wake_word and jev_tier_applies(jev_transcript):
        # Paid relevance arms share the same revision journal. Jev is never
        # silently skipped just because the caller is workerd.
        jev_discard = lambda: run_model('jev', lambda: jev_discard_probability(jev_transcript, record_outcome=True))

    def model_discards(on_error, adjacent):
        def call():
            failures = []
            with track_usage(uid, Features.CONVERSATION_DISCARD):
                discard = should_discard_conversation(
                    transcript if has_wake_word else plain,
                    duration_seconds=conversation_duration_seconds(conversation),
                    trusted_wake_word_markers=has_wake_word,
                    on_error=failures.append,
                    neighbor_gap_seconds=adjacent.gap_seconds if adjacent else None,
                    neighbor_position=adjacent.position if adjacent else None,
                )
            return None if failures else discard

        discard = run_model('nano', call)
        if discard is None:
            on_error(RuntimeError('relevance model unavailable'))
        return bool(discard)

    return decide_relevance(
        trigger=ProcessingTrigger.SYNC_UPDATE,
        texts=[segment.text for segment in segments],
        speech_seconds=sum(max(0.0, segment.end - segment.start) for segment in segments) if segments else None,
        has_photos=False,
        user_kept=user_kept,
        exempt=is_release_probe_uid(uid),
        trusted_wake_word=has_wake_word,
        model_discards=model_discards,
        calendar_retains=lambda: _calendar_overlap_retains_conversation(
            uid, conversation.started_at, conversation.finished_at
        ),
        neighbor=lambda: adjacent_conversation(uid, conversation, conversation.id),
        occasion_retains=lambda: occasion_retention(uid, conversation, conversation.id),
        jev_discard_probability=jev_discard,
        arm=arm,
        record_arm=relevance_experiment_active(),
    )
