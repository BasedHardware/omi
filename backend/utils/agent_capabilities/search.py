"""Owner-scoped bounded agent search over existing search and history authorities."""

from collections import Counter

from database import dream_history, vector_db
from models.agent_refs import base_ref, canonical_collection
from utils.agent_capabilities import reads as dream_reads
from utils.conversations.search import keyword_search_conversation_ids
from utils.agent_capabilities.guards import timestamp
from utils.agent_capabilities.session import serialized_bytes
from utils.executors import db_executor, llm_executor, run_blocking
from utils.memory.memory_service import MemoryService
from utils.observability.fallback import record_fallback

# One dead row must not walk the collection. Four id pages is enough to fill a
# readable history page; past that the page may be short.
_HISTORY_SCAN_CAP = 160


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


def _clip(value, limit):
    if isinstance(value, str):
        return value[:limit]
    return None


def project_search_row(row, *, person_id=None):
    """Fields the snippet and filters use. The rest of a capture is not retained.

    A speaker filter records the requested person wherever they appear. Other
    speaker ids are not retained once the snippet window is full.
    """
    if not isinstance(row, dict):
        return None
    stored = row.get('structured')
    structured = stored if isinstance(stored, dict) else {}
    segments = []
    remaining = 240
    matched_speaker = False
    for segment in row.get('transcript_segments') or []:
        if not isinstance(segment, dict):
            continue
        text = segment.get('text') if isinstance(segment.get('text'), str) else ''
        person = segment.get('person_id')
        if person_id and person == person_id:
            matched_speaker = True
        if remaining > 0 and text:
            kept = text[:remaining]
            item = {'text': kept}
            if person is not None:
                item['person_id'] = person
            segments.append(item)
            remaining -= len(kept)
        if matched_speaker and remaining <= 0:
            break
        if remaining <= 0 and not person_id:
            break
    if matched_speaker and not any(segment.get('person_id') == person_id for segment in segments):
        segments.append({'person_id': person_id})
    aliases = [_clip(alias, 240) for alias in (row.get('aliases') or []) if isinstance(alias, str)][:32]
    return {
        'id': row.get('id'),
        'name': _clip(row.get('name'), 64000),
        'content': _clip(row.get('content'), 64000),
        'description': _clip(row.get('description'), 64000),
        'user_title': _clip(row.get('user_title'), 240),
        'aliases': aliases,
        'created_at': row.get('created_at'),
        'captured_at': row.get('captured_at'),
        'valid_from': row.get('valid_from'),
        'entity_id': row.get('entity_id'),
        'subject_entity_id': row.get('subject_entity_id'),
        'structured': {
            'title': _clip(structured.get('title'), 240),
            'overview': _clip(structured.get('overview'), 240),
        },
        'transcript_segments': segments,
    }


class OwnerSearch:
    def __init__(self, uid, *, required_candidates=None):
        self.uid = uid
        self.required_candidates = required_candidates or {}

    async def read(self, ref):
        if ref in self.required_candidates:
            return await run_blocking(
                db_executor,
                dream_reads.read_required_intake_candidate,
                self.uid,
                base_ref(ref),
                self.required_candidates[ref],
            )
        return await run_blocking(db_executor, dream_reads.read_record, self.uid, base_ref(ref))

    async def hydrate(self, ref, request):
        return await run_blocking(
            db_executor,
            dream_reads.preview_record,
            self.uid,
            base_ref(ref),
            need_speakers=bool(request.person_ref),
        )

    async def _projected(self, ref, request):
        person_id = base_ref(request.person_ref).partition('/')[2] if request.person_ref else None
        try:
            full = await self.hydrate(ref, request)
        except Exception as error:
            # A missing, hidden, or locked row is unavailable. A transient store
            # fault fails the path so the search is incomplete and can be retried.
            if dream_reads.search_hydration_unavailable(error):
                return None
            raise
        if full is None:
            return None
        row = project_search_row(full, person_id=person_id)
        del full
        return row

    async def search(self, request, *, byte_budget=64000):
        query = request.vocabulary or request.query
        found = []
        skipped_refs = []
        unavailable_refs = []
        counts = Counter(hydrated=0, failed_paths=0, unavailable=0, budget_exhausted=0, embedding_token_upper_bound=0)
        cursors = {}
        for collection in dict.fromkeys(canonical_collection(name) for name in request.collections):
            refs = []
            rows = {}
            next_page = None
            history_cursor = None
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
                        next_page = 'lexical:' + str(page + 1)
                elif collection == 'conversations' and query and request.mode == 'semantic':
                    counts['embedding_token_upper_bound'] += len(query.encode()) * 3
                    if vector_db.index is None:
                        raise RuntimeError('agent_search_unconfigured')
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
                    # Skip ids that no longer resolve and keep paging until the
                    # readable page is full. Dead rows are not model budget.
                    loaded = []
                    after = request.cursor
                    examined = 0
                    while len(loaded) < 40 and examined < _HISTORY_SCAN_CAP:
                        ids = await run_blocking(
                            db_executor,
                            dream_history.history_page,
                            self.uid,
                            collection,
                            after=after,
                            limit=40,
                        )
                        if not ids:
                            break
                        short = len(ids) < 40
                        for key in ids:
                            examined += 1
                            after = key
                            ref = collection + '/' + key
                            row = await self._projected(ref, request)
                            if row is None:
                                counts['unavailable'] += 1
                                unavailable_refs.append(ref)
                                continue
                            loaded.append((ref, row))
                            if len(loaded) >= 40 or examined >= _HISTORY_SCAN_CAP:
                                break
                        if short or len(loaded) >= 40 or examined >= _HISTORY_SCAN_CAP:
                            break
                    refs = [ref for ref, _row in loaded]
                    rows = {ref: row for ref, row in loaded}
                    history_cursor = after if examined else None
                visited = 0
                page = refs[:40]
                for index, ref in enumerate(page):
                    visited += 1
                    if history_cursor is None and (
                        not (collection == 'conversations' and query and request.mode == 'lexical')
                        and request.mode != 'semantic'
                    ):
                        cursors[collection] = ref.partition('/')[2]
                    if history_cursor is None:
                        row = await self._projected(ref, request)
                        if row is None:
                            counts['unavailable'] += 1
                            unavailable_refs.append(ref)
                            continue
                    else:
                        row = rows[ref]
                    counts['hydrated'] += 1
                    if not matches(row, request):
                        continue
                    text = snippet(row)
                    if (
                        query
                        and (request.mode != 'semantic' or collection == 'people')
                        and not all(token.casefold() in snippet(row, limit=64000).casefold() for token in query.split())
                        and collection != 'conversations'
                    ):
                        continue
                    hit = {'ref': ref, 'snippet': text}
                    if serialized_bytes([*found, hit]) > byte_budget:
                        counts['budget_exhausted'] += 1
                        skipped_refs.append(ref)
                        continue
                    found.append(hit)
                    if len(found) >= request.limit:
                        # A preceding collection may have consumed result slots.
                        # Expose this page's unvisited tail rather than losing it.
                        skipped_refs.extend(page[index + 1 :])
                        break
                if history_cursor is not None:
                    cursors[collection] = history_cursor
                elif next_page and visited == len(page):
                    cursors[collection] = next_page
            except Exception:
                # Provider faults are explicit incomplete search, never a healthy
                # empty result. No arbitrary provider text enters diagnostics.
                counts['failed_paths'] += 1
                record_fallback(
                    component='agent_tools',
                    from_mode='agent_search',
                    to_mode='remaining_paths',
                    reason='other',
                    outcome='degraded',
                )
            if len(found) >= request.limit:
                break
        counts['read_bytes'] = serialized_bytes(found) if found else 0
        return {
            'results': found[: request.limit],
            'skipped_refs': list(dict.fromkeys(skipped_refs)),
            'unavailable_refs': list(dict.fromkeys(unavailable_refs)),
            'cursors': cursors,
            'counts': dict(counts),
            'complete': counts['failed_paths'] == 0 and not skipped_refs,
            'truncated': bool(skipped_refs),
        }
