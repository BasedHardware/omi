"""Unified Review orchestration; source lifecycles retain their existing owners."""

from datetime import datetime, timedelta, timezone

from database import candidates, conversations, review_changes, review_store as store
from models.action_item import TaskCreatePayload
from models.candidate import CandidateAction, CandidateStatus, CandidateSubjectKind
from models.review import (
    ChangeRef,
    ReviewEvidence,
    PersonRef,
    ReviewAnswer,
    ReviewAnswerReceipt,
    ReviewChange,
    ReviewItem,
    ReviewItemsResponse,
    SpeakerItem,
    TaskItem,
    TranscriptLine,
)
from models.speaker_tag_prompts import SpeakerTagPrompt, SpeakerTagPromptAnswer, SpeakerTagPromptAnswerRequest
from utils.speaker_tag_prompts import service as speakers
from utils.task_intelligence import candidate_service
from utils.task_intelligence.task_links import TaskLinkValidationError


def one_line(text: str | None, limit: int = 180) -> str | None:
    return ' '.join(text.split())[:limit] if text else None


def rank_review_items(items: list[ReviewItem], remaining: int) -> list[ReviewItem]:
    """Phase 1 heuristic: identity resolution wins by number of conversations unlocked.

    Speaker: 4 × affected conversations, identity merge: 3 × combined conversations,
    spelling: 2, task: 1. Stable oldest-first/id tie break. No LLM or paid computation.
    """

    def value(item):
        if item.speaker:
            return 4 * item.speaker.affected_conversation_count
        if item.same_person:
            return 3 * max(1, item.same_person.left.conversation_count + item.same_person.right.conversation_count)
        return 2 if item.spelling else 1

    return sorted(items, key=lambda item: (-value(item), item.created_at, item.item_id))[: min(3, max(0, remaining))]


def _speaker_item(uid: str, prompt: SpeakerTagPrompt) -> ReviewItem | None:
    conversation = conversations.get_conversation(uid, prompt.conversation_id)
    if not conversation or not conversations.is_visible_conversation(conversation):
        return None
    segments = conversation.get('transcript_segments') or []
    target = set(prompt.segment_ids)
    target_index = next((i for i, s in enumerate(segments) if s.get('id') in target), 0)
    start = conversation.get('started_at') or conversation.get('created_at') or datetime.now(timezone.utc)
    context = []
    for segment in segments[max(0, target_index - 1) : max(0, target_index - 1) + 3]:
        # Generic labels avoid leaking inferred names in a question quote/context.
        context.append(
            TranscriptLine(
                speaker_label=f"Speaker {segment.get('speaker_id', 0)}",
                text=one_line(segment.get('text')) or '',
                at=start + timedelta(seconds=float(segment.get('start') or 0)),
                is_target=segment.get('id') in target,
            )
        )
    # Existing prompts identify one conversation, not a voice cluster. Do not fabricate reach.
    return ReviewItem(
        item_id=f'speaker:{prompt.id}',
        kind='speaker',
        title='Who said this?',
        quote=one_line(prompt.excerpt),
        created_at=start,
        speaker=SpeakerItem(
            prompt_id=prompt.id,
            conversation_id=prompt.conversation_id,
            conversation_title=prompt.conversation_title,
            start=prompt.clip_start,
            end=prompt.clip_end,
            candidates=[PersonRef(person_id=c.person_id, name=c.name) for c in prompt.candidates[:3]],
            affected_conversation_count=1,
            context=context,
        ),
    )


def _task_item(uid: str, candidate) -> ReviewItem:
    payload = candidate.task_change
    workstream = (
        store.user(uid).collection('workstreams').document(candidate.workstream_id).get().to_dict()
        if candidate.workstream_id
        else None
    )
    evidence = None
    for ref in candidate.evidence_refs:
        if ref.kind.value != 'conversation':
            continue
        conversation = conversations.get_conversation(uid, ref.id)
        if not conversation or not conversations.is_visible_conversation(conversation):
            continue
        segments = conversation.get('transcript_segments') or []
        segment = next((s for s in segments if s.get('id') in (ref.transcript_segment_ids or [])), None)
        quote = one_line(segment.get('text')) if segment else None
        if quote and segment is not None:
            evidence = ReviewEvidence(
                quote=quote,
                speaker_label=f"Speaker {segment.get('speaker_id', 0)}",
                at=conversation.get('started_at'),
                conversation_id=ref.id,
                conversation_title=(conversation.get('structured') or {}).get('title') or '',
            )
        break
    return ReviewItem(
        item_id=f'task:{candidate.candidate_id}',
        kind='task',
        title='Add this task?',
        quote=evidence.quote if evidence else None,
        created_at=candidate.created_at,
        task=TaskItem(
            candidate_id=candidate.candidate_id,
            description=payload.description,
            due_at=payload.due_at,
            workstream_id=candidate.workstream_id,
            workstream_title=workstream.get('title') if workstream else None,
            evidence=evidence,
        ),
    )


def _sources(uid: str) -> list[tuple[ReviewItem, dict, str]]:
    from database.task_intelligence_control import get_task_workflow_control
    from utils.task_intelligence.chat_first_eligibility import resolve_task_intelligence_for_user

    result = []
    for prompt in speakers.get_prompts(uid).prompts:
        item = _speaker_item(uid, prompt)
        if item:
            source = prompt.model_dump(mode='python')
            result.append((item, source, store.fingerprint(source)))
    control = get_task_workflow_control(uid)
    rollout = resolve_task_intelligence_for_user(
        uid=uid, workflow_mode=control.workflow_mode, account_generation=control.account_generation
    )
    if rollout.intelligence_product_enabled:
        records = candidates.list_candidates(
            uid, status=CandidateStatus.pending, account_generation=control.account_generation, limit=100, offset=0
        )
        for candidate in records:
            if (
                candidate.subject_kind != CandidateSubjectKind.task
                or candidate.proposed_action != CandidateAction.create
                or not isinstance(candidate.task_change, TaskCreatePayload)
                or candidates.candidate_has_lapsed(candidate, now=datetime.now(timezone.utc))
            ):
                continue
            source = candidate.model_dump(mode='python')
            result.append((_task_item(uid, candidate), source, store.fingerprint(source)))
    for proposal in store.list_proposals(uid):
        item = ReviewItem.model_validate(proposal['item'])
        result.append((item, {}, proposal['evidence_version']))
    return result


def get_items(uid: str) -> ReviewItemsResponse:
    remaining = store.remaining_today(uid)
    if not remaining:
        return ReviewItemsResponse(items=[], remaining_today=0)
    eligible = []
    for item, source, version in _sources(uid):
        if store.offer_item(uid, item, source, version):
            eligible.append(item)
    return ReviewItemsResponse(items=rank_review_items(eligible, remaining), remaining_today=remaining)


def answer_item(uid: str, item_id: str, answer: ReviewAnswer, *, schedule=None) -> ReviewAnswerReceipt:
    kind = item_id.partition(':')[0]
    if not answer.not_sure and getattr(answer, kind, None) is None:
        raise store.ReviewConflict('Answer kind does not match item')
    state = store.begin_answer(uid, item_id, store.fingerprint(answer.model_dump(mode='json')))
    if state['retry']:
        return ReviewAnswerReceipt(
            item_id=item_id, applied=state['applied'], remaining_today=store.remaining_today(uid)
        )
    item = ReviewItem.model_validate(state['item'])
    uncertain = answer.not_sure or bool(answer.same_person and answer.same_person.decision == 'not_sure')
    applied = False
    try:
        if uncertain:
            # Do not call speaker skip: it permanently marks that source answered.
            # Review stores an evidence version, permitting a new-evidence question.
            pass
        elif item.speaker:
            prompt = SpeakerTagPrompt.model_validate(state['source'])
            payload = answer.speaker
            if payload is None:
                raise store.ReviewConflict('Speaker answer required')
            choice = (
                SpeakerTagPromptAnswer.me
                if payload.is_me
                else SpeakerTagPromptAnswer.new_person if payload.new_person_name else SpeakerTagPromptAnswer.person
            )
            request = SpeakerTagPromptAnswerRequest(
                prompt_id=prompt.id,
                kind=prompt.kind,
                origin=prompt.origin,
                conversation_id=prompt.conversation_id,
                speaker_id=prompt.speaker_id,
                segment_ids=prompt.segment_ids,
                answer=choice,
                person_id=payload.person_id,
                name=payload.new_person_name,
                suggested_person_id=prompt.suggested_person_id,
            )
            speakers.apply_answer(uid, request, schedule=schedule)
            applied = True
        elif item.task:
            from database.task_intelligence_control import get_task_workflow_control

            generation = get_task_workflow_control(uid).account_generation
            if generation != state['source']['account_generation']:
                raise store.ReviewConflict('Candidate generation changed')
            payload = answer.task
            if payload is None:
                raise store.ReviewConflict('Task answer required')
            if payload.decision == 'accept':
                edits = {
                    key: value
                    for key, value in payload.model_dump(mode='python', exclude_unset=True).items()
                    if key in {'edited_description', 'due_at', 'workstream_id'}
                    and (key != 'edited_description' or value is not None)
                }
                if edits:
                    candidate_service.accept_candidate(
                        uid, item.task.candidate_id, account_generation=generation, review_edits=edits
                    )
                else:
                    candidate_service.accept_candidate(uid, item.task.candidate_id, account_generation=generation)
            else:
                candidate_service.reject_candidate(
                    uid, item.task.candidate_id, reason=payload.dismiss_reason, account_generation=generation
                )
            applied = True
        elif item.same_person and answer.same_person and answer.same_person.decision == 'yes':
            from utils.entity_pages import resolve_entity

            left = resolve_entity(uid, item.same_person.left.entity_id)
            right = resolve_entity(uid, item.same_person.right.entity_id)
            if left['type'] != right['type']:
                raise store.ReviewConflict('Entity types differ')
            change = ReviewChange(
                change_id=f'review:{store.safe_id(item_id)}',
                kind='other',
                title=f"Merge {left['name']} and {right['name']}",
                reason=item.same_person.reason,
                refs=[
                    ChangeRef(type=left['type'], id=left['entity_id'], label=left['name']),
                    ChangeRef(type=right['type'], id=right['entity_id'], label=right['name']),
                ],
                created_at=datetime.now(timezone.utc),
            )
            review_changes.merge_review_entities(
                uid,
                change,
                left['entity_id'],
                right['entity_id'],
                edit_key='merge:' + ':'.join(sorted([left['entity_id'], right['entity_id']])),
            )
            applied = True
        elif item.spelling:
            from utils.entity_pages import save_user_fact

            if answer.spelling is None:
                raise store.ReviewConflict('Spelling answer required')
            value = answer.spelling.value.strip()
            if not value or (not item.spelling.allow_custom and value not in item.spelling.options):
                raise store.ReviewConflict('Spelling is not an allowed option')
            save_user_fact(
                uid,
                f'vocabulary:{item.spelling.term_id}',
                value,
                action_id=f'review:{store.safe_id(item_id)}',
                predicate='vocabulary',
            )
            applied = True
    except (
        store.ReviewConflict,
        store.ReviewNotFound,
        speakers.TagPromptInvalid,
        candidates.CandidateStoreError,
        TaskLinkValidationError,
    ):
        store.release_failed_answer(uid, item_id)
        raise
    except LookupError as exc:
        store.release_failed_answer(uid, item_id)
        raise store.ReviewNotFound('Person not found') from exc
    return store.finish_answer(uid, item_id, applied=applied, uncertain=uncertain)
