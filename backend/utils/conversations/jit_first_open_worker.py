"""Execution of one claimed first-open obligation under live authority."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional

from models.app import UsageHistoryType
from models.other import Person
from utils.metrics import record_jit_first_open


def run_first_open_derived_work(uid: str, conversation_data: dict[str, Any], token: str) -> None:
    # Import lazily to preserve the large processing module's existing test
    # seams without creating an import cycle at router startup.
    from utils.conversations import process_conversation as processing

    conversation = processing.deserialize_conversation(conversation_data)
    obligation = conversation_data.get('jit_first_open') or {}
    raw_effects = obligation.get('effects')
    states = dict(raw_effects) if isinstance(raw_effects, Mapping) else {}
    source = getattr(conversation.source, 'value', conversation.source)

    def complete_state(effect: str) -> bool:
        state = states.get(effect)
        return isinstance(state, Mapping) and state.get('state') == 'complete'

    def authorize(effect: str) -> None:
        plan = processing.resolve_authorized_first_open_plan(uid=uid, source=str(source or ''), force_refresh=True)
        if not plan.defer_derived_work or not processing.conversations_db.first_open_effect_is_authorized(
            uid, conversation.id, token, effect
        ):
            raise RuntimeError(f'first-open authority suspended before {effect}')

    def complete(effect: str) -> None:
        try:
            authorize(effect)
            if not processing.conversations_db.complete_first_open_effect(uid, conversation.id, token, effect):
                raise RuntimeError(f'first-open lease lost while completing {effect}')
            states[effect] = {'state': 'complete'}
            try:
                record_jit_first_open(event='complete', effect=effect)
            except Exception:
                pass
        except Exception:
            try:
                record_jit_first_open(event='fail', effect=effect)
            except Exception:
                pass
            raise

    if conversation.discarded:
        for effect in processing.conversations_db.FIRST_OPEN_EFFECTS:
            if not complete_state(effect):
                complete(effect)
        return

    people: list[Person] = []
    person_ids = conversation.get_person_ids()
    if person_ids:
        people = [Person(**item) for item in processing.users_db.get_people_by_ids(uid, list(set(person_ids)))]

    if not complete_state('folder_assignment'):
        authorize('folder_assignment')
        folder_patch: Optional[Mapping[str, Any]] = None
        if not conversation.folder_id:
            folders = processing.folders_db.get_folders(uid)
            if not folders:
                folders = processing.folders_db.initialize_system_folders(uid)
            if folders and conversation.structured:
                category = conversation.structured.category.value if conversation.structured.category else 'other'
                with processing.track_usage(uid, processing.Features.CONVERSATION_FOLDER):
                    folder_id, _confidence, _reasoning = processing.assign_conversation_to_folder(
                        title=conversation.structured.title or '',
                        overview=conversation.structured.overview or '',
                        category=category,
                        user_folders=folders,
                        category_folder_id=processing.folders_db.resolve_category_folder_id(category, folders),
                    )
                if folder_id:
                    conversation.folder_id = folder_id
                    folder_patch = {'folder_id': folder_id}
        if folder_patch:
            authorize('folder_assignment')
            if not processing.conversations_db.commit_first_open_conversation_patch(
                uid, conversation.id, token, 'folder_assignment', folder_patch
            ):
                raise RuntimeError('first-open authority lost while persisting folder assignment')
        if conversation.folder_id:
            authorize('folder_assignment')
            if not processing.conversations_db.commit_first_open_folder_count(
                uid, conversation.id, token, conversation.folder_id
            ):
                raise RuntimeError('first-open authority lost while refreshing folder count')
            complete('folder_assignment')

    if complete_state('app_fanout'):
        return
    authorize('app_fanout')

    def commit_result(app_id: str, patch: Mapping[str, Any]) -> bool:
        authorize('app_fanout')
        return processing.conversations_db.commit_first_open_app_result(uid, conversation.id, token, app_id, patch)

    def commit_usage(app_id: str, usage_type: UsageHistoryType) -> bool:
        authorize('app_fanout')
        return processing.conversations_db.commit_first_open_app_usage(
            uid, conversation.id, token, app_id, usage_type.value
        )

    # A crash may leave a durable app result before its usage attribution. Repair
    # that suffix before selection filters the already-computed app from replay.
    for result in conversation.apps_results:
        if not result.app_id:
            raise RuntimeError('app fanout first-open result is missing an app id')
        result_patch = {
            'apps_results': [item.dict() for item in conversation.apps_results],
            'suggested_summarization_apps': conversation.suggested_summarization_apps,
        }
        if not commit_result(result.app_id, result_patch) or not commit_usage(
            result.app_id, UsageHistoryType.memory_created_prompt
        ):
            raise RuntimeError('app fanout first-open receipt repair failed')

    succeeded = processing.trigger_conversation_apps(
        uid,
        conversation,
        is_reprocess=False,
        usage_attribution=processing.AppUsageAttribution.AUTOMATIC_PROCESSING,
        language_code=conversation.language or 'en',
        people=people,
        preserve_existing_results=True,
        resumable_result_commit=commit_result,
        resumable_usage_commit=commit_usage,
        resumable_effect_authorizer=lambda: authorize('app_fanout'),
    )
    if not succeeded:
        raise RuntimeError('app fanout first-open effect failed')
    patch = (
        {
            'apps_results': [result.dict() for result in conversation.apps_results],
            'suggested_summarization_apps': conversation.suggested_summarization_apps,
        }
        if processing.conversation_apps_opt_in_only()
        or conversation.apps_results
        or conversation.suggested_summarization_apps
        else None
    )
    if patch and not conversation.apps_results:
        authorize('app_fanout')
        if not processing.conversations_db.commit_first_open_conversation_patch(
            uid, conversation.id, token, 'app_fanout', patch
        ):
            raise RuntimeError('first-open authority lost while persisting app selection')
    complete('app_fanout')
