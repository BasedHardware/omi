"""Bounded, owner-scoped entity projections over the existing graph and ledger.

Person identity is person:{people id}; projects use workstream ids verbatim.
Organization already fits knowledge_nodes.node_type (an unrestricted string),
so no migration is needed. Summaries are a derived dream cache only.
"""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from google.cloud.firestore_v1.base_query import FieldFilter

from database import action_items, conversations, knowledge_graph, review_queries, review_store as store, users
from models.entity_pages import ConversationRef, EntityPage, Fact, FactSource, TaskRef
from models.review import EntityRef, ReviewItem

MAX_RELATED = 30


def _id(value: str) -> str:
    if not value or '/' in value or len(value) > 128:
        raise store.ReviewNotFound('Invalid entity id')
    return value


def resolve_entity(uid: str, entity_id: str) -> dict:
    _id(entity_id)
    node = knowledge_graph.get_knowledge_node(uid, entity_id) or {}
    seen = set()
    while node.get('redirect_entity_id'):
        if entity_id in seen or len(seen) >= 8:
            raise store.ReviewConflict('Entity redirect cycle')
        seen.add(entity_id)
        entity_id = _id(node['redirect_entity_id'])
        node = knowledge_graph.get_knowledge_node(uid, entity_id) or {}
    if entity_id.startswith('person:'):
        person = users.get_person(uid, entity_id.removeprefix('person:'))
        if not person:
            raise store.ReviewNotFound('Person not found')
        return dict(
            node,
            entity_id=entity_id,
            type='person',
            name=person['name'],
            subtitle=person.get('subtitle') or person.get('role'),
            organization_id=person.get('organization_id') or node.get('organization_id'),
        )
    workstream = store.user(uid).collection('workstreams').document(entity_id).get().to_dict()
    if workstream and workstream.get('status') not in {'deleted', 'cancelled'}:
        from database.task_intelligence_control import get_task_workflow_control

        if workstream.get('account_generation', 0) != get_task_workflow_control(uid).account_generation:
            raise store.ReviewNotFound('Project generation changed')
        return dict(
            node,
            entity_id=entity_id,
            type='project',
            name=workstream['title'],
            subtitle=workstream.get('objective'),
            organization_id=node.get('organization_id'),
        )
    if node.get('node_type') == 'organization':
        return dict(node, entity_id=entity_id, type='organization', name=node.get('label', entity_id))
    raise store.ReviewNotFound('Entity not found')


def entity_ref(uid: str, entity_id: str) -> EntityRef:
    node = resolve_entity(uid, entity_id)
    return EntityRef(entity_id=node['entity_id'], type=node['type'], name=node['name'])


def project_refs(uid: str) -> list[EntityRef]:
    from database.task_intelligence_control import get_task_workflow_control

    generation = get_task_workflow_control(uid).account_generation
    result = []
    for row in store.user(uid).collection('workstreams').order_by('__name__').limit(500).stream():
        data = row.to_dict()
        if data.get('account_generation', 0) == generation and data.get('status') not in {'deleted', 'cancelled'}:
            result.append(EntityRef(entity_id=row.id, type='project', name=data['title']))
    return result


def _facts(uid: str, entity_ids: list[str]) -> tuple[list[Fact], list[Fact], set[str]]:
    from utils.memory.memory_service import MemoryService

    service = MemoryService(db_client=store.client())
    ids = set()
    for entity_id in entity_ids:
        for spec, date in [
            (review_queries.ENTITY_FACTS, 'created_at'),
            (review_queries.CANONICAL_FACTS, 'captured_at'),
        ]:
            query = spec.build(
                store.user(uid).collection(spec.collection_group),
                {'entity_id': entity_id},
                field_filter_factory=FieldFilter,
            )
            ids.update(s.id for s in query.order_by(date, direction='DESCENDING').limit(MAX_RELATED).stream())
    from models.product_memory import MemoryAccessPolicy
    from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items
    from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items_by_ids
    from utils.memory.canonical_memory_adapter import memory_item_to_memorydb

    canonical = fetch_authoritative_product_memory_items_by_ids(uid, sorted(ids)[:100], db_client=store.client())
    visible = {
        item.memory_id: item
        for item in filter_canonical_default_visible_items(
            canonical, policy=MemoryAccessPolicy.for_omi_chat(archive_capability=False), now=datetime.now(timezone.utc)
        )
    }
    canonical_ids = {item.memory_id for item in canonical}
    facts, decisions, conversation_ids = [], [], set()
    for memory_id in sorted(ids)[:100]:
        if memory_id in canonical_ids and memory_id not in visible:
            continue
        try:
            row = memory_item_to_memorydb(visible[memory_id]) if memory_id in visible else service.fetch(uid, memory_id)
        except HTTPException as exc:
            if exc.status_code not in {402, 404}:
                raise
            continue
        if row is None or row.user_review is False or row.is_locked:
            continue
        if row.subject_entity_id not in entity_ids:
            continue
        data = row.model_dump(mode='python')
        source_id = data.get('conversation_id')
        evidence = data.get('evidence') or []
        if source_id:
            conversation = conversations.get_conversation(uid, source_id)
            if not conversation or not conversations.is_visible_conversation(conversation):
                continue
            conversation_ids.add(source_id)
            source = FactSource(
                kind='conversation',
                label=_title(conversation),
                conversation_id=source_id,
                at=conversation.get('started_at') or row.created_at,
            )
        else:
            source_type = evidence[0].get('source_type', '') if evidence and isinstance(evidence[0], dict) else ''
            kind = (
                'user'
                if row.manually_added or source_type.startswith('explicit_user')
                else 'screen' if 'screen' in source_type else 'chat'
            )
            source = FactSource(
                kind=kind, label={'user': 'You', 'screen': 'Screen', 'chat': 'Chat'}[kind], at=row.created_at
            )
        fact = Fact(fact_id=memory_id, text=row.content, source=source)
        facts.append(fact)
        if data.get('predicate') == 'decision' or data.get('category') == 'decision':
            decisions.append(fact)
    return facts[:MAX_RELATED], decisions[:MAX_RELATED], conversation_ids


def _title(conversation: dict) -> str:
    return conversation.get('user_title') or (conversation.get('structured') or {}).get('title') or ''


def _entity_ids_for_conversation(uid: str, conversation: dict, *, graph_citations: bool = True) -> list[str]:
    ids = list(conversation.get('entity_ids') or [])
    for segment in conversation.get('transcript_segments') or []:
        if segment.get('person_id'):
            ids.append(f"person:{segment['person_id']}")
    if conversation.get('workstream_id'):
        ids.append(conversation['workstream_id'])
    if not graph_citations:
        return list(dict.fromkeys(ids))
    cid = conversation.get('id')
    # Existing graph citations are an additional source; no substring name matching.
    from database import memories

    memory_ids = set(memories.get_memory_ids_for_conversation(uid, cid)) if cid else set()
    for node in knowledge_graph.get_knowledge_nodes(uid):
        if cid in node.get('conversation_ids', []) or memory_ids.intersection(node.get('memory_ids', [])):
            ids.append(node['id'])
    return list(dict.fromkeys(ids))


def conversation_entities(uid: str, conversation_id: str) -> list[EntityRef]:
    conversation = conversations.get_conversation(uid, _id(conversation_id))
    if not conversation or not conversations.is_visible_conversation(conversation):
        raise store.ReviewNotFound('Conversation not found')
    refs = {}
    for entity_id in _entity_ids_for_conversation(uid, conversation)[:100]:
        try:
            ref = entity_ref(uid, entity_id)
        except store.ReviewNotFound:
            continue
        refs[ref.entity_id] = ref
    return sorted(refs.values(), key=lambda ref: (ref.type == 'person', ref.name.casefold(), ref.entity_id))[:4]


def get_entity_page(uid: str, entity_id: str) -> EntityPage:
    node = resolve_entity(uid, entity_id)
    entity_id = node['entity_id']
    identities = [entity_id, *node.get('merged_entity_ids', [])][:10]
    cache = store.decode_doc(uid, store.user(uid).collection('entity_pages').document(entity_id).get().to_dict()) or {}
    related = {}
    for edge in knowledge_graph.get_knowledge_edges(uid):
        if edge.get('source_id') in identities:
            other = edge.get('target_id')
        elif edge.get('target_id') in identities:
            other = edge.get('source_id')
        else:
            continue
        try:
            ref = entity_ref(uid, other)
        except store.ReviewNotFound:
            continue
        if ref.entity_id not in identities:
            related[ref.entity_id] = ref
    organization = None
    if node['type'] != 'organization':
        org_id = node.get('organization_id')
        if org_id:
            try:
                organization = entity_ref(uid, org_id)
            except store.ReviewNotFound:
                pass
        if organization is None:
            organization = next((r for r in related.values() if r.type == 'organization'), None)
    facts, decisions, conversation_ids = _facts(uid, identities)
    conversation_ids.update(node.get('conversation_ids', [])[:MAX_RELATED])
    open_tasks = []
    if node['type'] == 'project':
        query = review_queries.PROJECT_TASKS.build(
            store.user(uid).collection('action_items'), {'entity_id': entity_id}, field_filter_factory=FieldFilter
        )
        from database.task_intelligence_control import get_task_workflow_control

        generation = get_task_workflow_control(uid).account_generation
        for snapshot in query.order_by('created_at', direction='DESCENDING').limit(100).stream():
            task = action_items.get_action_item(uid, snapshot.id)
            if not task or task.get('status', 'active') != 'active' or task.get('account_generation', 0) != generation:
                continue
            open_tasks.append(
                TaskRef(
                    task_id=snapshot.id,
                    description=task['description'],
                    owner_label=task.get('owner_label') or task.get('owner'),
                    due_at=task.get('due_at'),
                    waiting_on=task.get('waiting_on'),
                )
            )
            if task.get('conversation_id'):
                conversation_ids.add(task['conversation_id'])
    # Existing speaker-tagged conversations need no graph node backfill.
    for conversation in conversations.get_conversations(uid, limit=100):
        if set(_entity_ids_for_conversation(uid, conversation, graph_citations=False)).intersection(identities):
            conversation_ids.add(conversation['id'])
    recent = []
    for cid in sorted(conversation_ids)[:100]:
        conversation = conversations.get_conversation(uid, cid)
        if not conversation or not conversations.is_visible_conversation(conversation):
            continue
        start = conversation.get('started_at') or conversation.get('created_at')
        end = conversation.get('finished_at') or start
        if start:
            recent.append(
                ConversationRef(
                    conversation_id=cid,
                    title=_title(conversation),
                    started_at=start,
                    duration_seconds=max(0, int((end - start).total_seconds())),
                )
            )
    pending = None
    for proposal in store.list_proposals(uid):
        item = ReviewItem.model_validate(proposal['item'])
        if item.same_person and {item.same_person.left.entity_id, item.same_person.right.entity_id}.intersection(
            identities
        ):
            if store.offer_item(uid, item, {}, proposal['evidence_version']):
                pending = item
                break
    return EntityPage(
        entity_id=entity_id,
        type=node['type'],
        name=node['name'],
        subtitle=node.get('subtitle'),
        organization=organization,
        summary=cache.get('summary'),
        summary_updated_at=cache.get('updated_at'),
        people=[r for r in related.values() if r.type == 'person'][:MAX_RELATED],
        projects=[r for r in related.values() if r.type == 'project'][:MAX_RELATED],
        facts=facts,
        decisions=decisions if node['type'] == 'project' else [],
        open_tasks=open_tasks[:MAX_RELATED],
        recent_conversations=sorted(recent, key=lambda c: c.started_at, reverse=True)[:10],
        pending_question=pending,
    )


def write_entity_summary(uid: str, entity_id: str, summary: str, *, updated_at: datetime | None = None) -> None:
    """Dream writer: the cache never replaces authoritative facts."""
    store.require_enabled()
    entity_id = resolve_entity(uid, entity_id)['entity_id']
    if len(summary) > 16000:
        raise ValueError('Entity summary is too long')
    store.user(uid).collection('entity_pages').document(entity_id).set(
        store.encode_doc(uid, {'summary': summary, 'updated_at': updated_at or datetime.now(timezone.utc)}), merge=True
    )


def save_user_fact(
    uid: str, entity_id: str, text: str, *, action_id: str | None = None, slot: str | None = None
) -> str:
    """Canonical direct-user append, authority 600; never a legacy projection write."""
    from models.product_memory import LedgerWriteReason, MemorySubjectScope
    from utils.memory.canonical_memory_adapter import mint_direct_user_write_authority
    from utils.memory.knowledge_ledger import LedgerProvenance, save_fact

    return save_fact(
        uid,
        text,
        provenance=LedgerProvenance(
            source_id=entity_id, source_type='explicit_user_statement', action_id=action_id or uuid4().hex
        ),
        write_reason=LedgerWriteReason.direct_user_statement,
        subject_entity_id=entity_id,
        subject_scope=MemorySubjectScope.third_party,
        slot=slot,
        user_asserted=True,
        db_client=store.client(),
        _direct_user_authority=mint_direct_user_write_authority(),
    )


def correct_entity(uid: str, entity_id: str, text: str) -> None:
    node = resolve_entity(uid, entity_id)
    save_user_fact(uid, node['entity_id'], text)
