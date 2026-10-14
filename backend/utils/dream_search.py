"""Owner-scoped bounded Dream search over existing search and history authorities."""

from collections import Counter

from database import dream_history, vector_db
from models.dream_refs import base_ref
from utils import dream_reads
from utils.conversations.search import keyword_search_conversation_ids
from utils.dream_guards import timestamp
from utils.executors import db_executor, llm_executor, run_blocking
from utils.memory.memory_service import MemoryService
from utils.observability.fallback import record_fallback


def snippet(row, *, limit=240):
    structured = row.get('structured') or {}
    parts = [
        row.get('name'),
        row.get('content'),
        row.get('description'),
        row.get('user_title'),
        structured.get('title'),
        structured.get('overview'),
    ]
    parts.extend(segment.get('text') for segment in row.get('transcript_segments') or [])
    parts.extend(row.get('aliases') or [])
    return ' '.join(str(part).strip() for part in parts if part)[:limit]


def matches(row, request):
    date = timestamp(row.get('created_at') or row.get('captured_at') or row.get('valid_from'))
    if (request.start or request.end) and (
        date is None or (request.start and date < request.start) or (request.end and date > request.end)
    ):
        return False
    if request.person_ref:
        person = base_ref(request.person_ref).partition('/')[2]
        if not (
            row.get('id') == person
            or row.get('entity_id') == 'person:' + person
            or row.get('subject_entity_id') == 'person:' + person
            or any(segment.get('person_id') == person for segment in row.get('transcript_segments') or [])
        ):
            return False
    return True


class OwnerSearch:
    def __init__(self, uid):
        self.uid = uid

    async def read(self, ref):
        return await run_blocking(db_executor, dream_reads.read_record, self.uid, base_ref(ref))

    async def search(self, request):
        query = request.vocabulary or request.query
        found = []
        counts = Counter()
        cursors = {}
        for collection in dict.fromkeys(request.collections):
            refs = []
            try:
                if collection == 'conversations' and query and request.mode == 'lexical':
                    page = (
                        int(request.cursor.partition(':')[2])
                        if request.cursor and request.cursor.startswith('lexical:')
                        else 1
                    )
                    ids = await run_blocking(
                        db_executor,
                        keyword_search_conversation_ids,
                        uid=self.uid,
                        query=query,
                        limit=request.limit,
                        raise_on_error=True,
                        page=page,
                        start_date=int(request.start.timestamp()) if request.start else None,
                        end_date=int(request.end.timestamp()) if request.end else None,
                    )
                    refs = ['conversations/' + key for key in ids]
                    if len(ids) >= request.limit:
                        cursors[collection] = 'lexical:' + str(page + 1)
                elif collection == 'conversations' and query and request.mode == 'semantic':
                    counts['embedding_token_upper_bound'] += len(query.encode()) * 3
                    ids = await run_blocking(
                        llm_executor,
                        vector_db.query_vectors,
                        query,
                        self.uid,
                        k=request.limit,
                        starts_at=int(request.start.timestamp()) if request.start else None,
                        ends_at=int(request.end.timestamp()) if request.end else None,
                    )
                    refs = ['conversations/' + key for key in ids]
                elif collection == 'memory_items' and query and request.mode == 'semantic':
                    counts['embedding_token_upper_bound'] += len(query.encode()) * 6
                    hits = await run_blocking(
                        llm_executor, MemoryService().search, self.uid, query, limit=request.limit
                    )
                    refs = ['memory_items/' + hit.memory.id for hit in hits]
                elif collection == 'action_items' and query and request.mode == 'semantic':
                    counts['embedding_token_upper_bound'] += len(query.encode()) * 3
                    ids = await run_blocking(
                        llm_executor, vector_db.search_action_items_by_vector, self.uid, query, limit=request.limit
                    )
                    refs = ['action_items/' + key for key in ids if key]
                else:
                    # Metadata pages are bounded even for people/task lexical or
                    # temporal browsing; model-directed continuation hunts history.
                    ids = await run_blocking(
                        db_executor, dream_history.history_page, self.uid, collection, after=request.cursor, limit=40
                    )
                    refs = [collection + '/' + key for key in ids]
                for ref in refs[:40]:
                    if (
                        not (collection == 'conversations' and query and request.mode == 'lexical')
                        and request.mode != 'semantic'
                    ):
                        cursors[collection] = ref.partition('/')[2]
                    row = await self.read(ref)
                    counts['hydrated'] += 1
                    if row is None or not matches(row, request):
                        continue
                    text = snippet(row)
                    if (
                        query
                        and (request.mode != 'semantic' or collection == 'people')
                        and not all(token.casefold() in snippet(row, limit=64000).casefold() for token in query.split())
                        and collection != 'conversations'
                    ):
                        continue
                    found.append({'ref': ref, 'snippet': text})
                    if len(found) >= request.limit:
                        break
            except Exception:
                # Provider faults are explicit incomplete search, never a healthy
                # empty result. No arbitrary provider text enters diagnostics.
                counts['failed_paths'] += 1
                record_fallback(
                    component='agent_tools',
                    from_mode='dream_search',
                    to_mode='remaining_paths',
                    reason='other',
                    outcome='degraded',
                )
            if len(found) >= request.limit:
                break
        return {
            'results': found[: request.limit],
            'cursors': cursors,
            'counts': dict(counts),
            'complete': counts['failed_paths'] == 0,
        }
