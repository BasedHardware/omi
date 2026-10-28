"""Notes-agent adapter: the production serving stack replayed over a frozen owner snapshot.

Everything semantic — packet build and selection (packet-v2 pinned to the serving
default), identity wiring, the length module, budget, checks and repairs — is
imported unchanged from the arm tree's ``utils/``. Only the data seams (snapshot
reads instead of Firestore, lexical search instead of the external index) and the
HTTP transport (the bench's spend-guarded local gateway) are replaced. External
semantic search is approximated lexically over the frozen snapshot; the snapshot
carries no speaker evidence bundle.

The owner uid and snapshot path come from the environment and are never
defaulted; no identifier lives in this file.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from testing.owner_lab import invariants
from testing.owner_lab import replay_bench
from testing.owner_lab.store import Snapshot, parse_time, score, terms

LANE = 'omi:auto:conv-structure'
# Packet-v2 and action-items-v2 pinned to the unset production default: shadow,
# zero serve percent — verified equal to the unset parser in qualify().
PINNED_DEFAULTS = {
    'NOTES_PACKET_V2_MODE': 'shadow',
    'NOTES_PACKET_V2_MODE_SERVE_PERCENT': '0',
    'ACTION_ITEMS_V2_MODE': 'shadow',
    'ACTION_ITEMS_V2_MODE_SERVE_PERCENT': '0',
}
BASE_ENV = {
    'CONVERSATION_NOTES_AGENT_ENABLED': 'true',
    'CONVERSATION_NOTES_AGENT_PERCENT': '100',
    'SPEAKER_IDENTITY_REPAIR_ENABLED': 'true',
    'OMI_SHAPED_AGENT_MODE': 'on',
    'ENCRYPTION_SECRET': 'owner-lab-dummy-key-never-used-00000000',
    'OPENAI_API_KEY': 'snapshot-only',
}
REPAIR_KINDS = (
    'accepted_with_problems',
    'participant_dropped',
    'unsupported_speaker_identity',
    'rejected_format',
    'rejected_content',
    'rejected_evidence',
)
# Frozen clock for packet windows; matches the 2026-10 snapshot era.
FIXED_NOW = datetime(2026, 10, 28, 5, 0, tzinfo=timezone.utc)


def build_adapter() -> 'NotesAdapter':
    return NotesAdapter()


def tier(words: int) -> str:
    return 'short' if words < 1500 else 'medium' if words < 5000 else 'long'


def data_url(path: str) -> str:
    return 'data:image/jpeg;base64,' + base64.b64encode(Path(path).read_bytes()).decode()


def offset(start: datetime, at: Any) -> str:
    moment = parse_time(at)
    if moment is None:
        return '00:00'
    seconds = max(0, int((moment - start).total_seconds()))
    return f'{seconds // 60:02d}:{seconds % 60:02d}'


class NotesAdapter(replay_bench.ReplayAdapter):
    """Production serving orchestrator; only database/index/HTTP seams replaced."""

    def __init__(self) -> None:
        for key in list(os.environ):
            if key in ('GOOGLE_APPLICATION_CREDENTIALS', 'SERVICE_ACCOUNT_JSON') or key.endswith('_SERVE_UID_SHA256S'):
                os.environ.pop(key, None)
        self.uid = os.environ.get(replay_bench.UID_ENV) or self._required(replay_bench.UID_ENV)
        snapshot = os.environ.get(replay_bench.SNAPSHOT_ENV) or self._required(replay_bench.SNAPSHOT_ENV)
        os.environ.update(BASE_ENV)
        os.environ.update(PINNED_DEFAULTS)
        logging.disable(logging.CRITICAL)
        self.snap = Snapshot.load(snapshot)
        self.cases = (
            invariants.load_cases(os.environ[replay_bench.CASES_ENV]) if os.environ.get(replay_bench.CASES_ENV) else {}
        )
        self.result: Any = None
        self.error: BaseException | None = None
        self.invocation: dict[str, Any] | None = None
        self.packet_seen: dict[str, Any] | None = None
        self.raw_calls: list[tuple[str, str]] = []
        self._wire_serving()

    @staticmethod
    def _required(name: str) -> str:
        raise SystemExit(f'{name} must point outside the repository; it is never defaulted')

    def _wire_serving(self) -> None:
        from utils.conversations import meeting_context_pack as pack
        from utils.conversations import notes_agent_tools as tools
        from utils.llm import notes_agent as agent
        from utils.llm import notes_agent_policy as policy
        from utils.llm import notes_agent_prompt as prompt
        from utils.llm import notes_agent_serving as serving
        from utils.llm import notes_packet as packet

        self.agent, self.policy, self.prompt = agent, policy, prompt
        self.tools, self.serving, self.packet = tools, serving, packet
        tools.load_people_documents = lambda _: self.snap.people[:100]
        tools.get_ai_user_profile = lambda _: self.snap.profile.get('ai_user_profile') or {}
        tools.calendar_db.get_meetings_in_time_range = self.calendar
        tools.calendar_db.list_meetings = self.meetings
        tools.screen_activity_db.get_screen_activity = self.screen
        tools.action_items_db.get_action_items = self.tasks
        pack.conversations_db.get_conversations_without_photos = self.conversations
        pack.load_people_documents = tools.load_people_documents
        packet.get_evidence = lambda *_: None  # no speaker evidence bundle in the snapshot
        packet.notes_people = lambda *_: self.snap.people[:100]

        class _FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz: Any = None) -> Any:
                return FIXED_NOW.astimezone(tz) if tz else FIXED_NOW.replace(tzinfo=None)

        packet.datetime = _FrozenDateTime
        outer = self

        class _LocalSearch:
            def __init__(self, uid: str) -> None:
                pass

            async def search(self, request: Any, byte_budget: Any) -> dict[str, Any]:
                return outer.search(request)

            async def read(self, ref: str) -> Any:
                return outer.snap.conversations.get(ref.partition('/')[2]) if ref.startswith('conversations/') else None

        tools.OwnerSearch = _LocalSearch
        serving.transport_skip_reason = lambda *_: None
        serving.model_supports_explicit_cache = lambda _: True

        @asynccontextmanager
        async def _isolate(model: Any):
            yield model

        serving.isolated_notes_model = _isolate
        original_run = serving.run_notes_agent

        async def _run(**kwargs: Any) -> Any:
            outer.invocation = kwargs
            try:
                outer.result = await original_run(**kwargs)
                return outer.result
            except BaseException as error:  # noqa: BLE001 - captured for qualification sentinels
                outer.error = error
                raise

        serving.run_notes_agent = _run
        original_select = serving.select_notes_packet

        def _select(*args: Any, **kwargs: Any) -> Any:
            outer.packet_seen = original_select(*args, **kwargs)
            return outer.packet_seen

        serving.select_notes_packet = _select

    # ---- snapshot seam implementations (aggregates; no identifiers logged) ----

    def calendar(self, uid: Any, start_time: Any, end_time: Any) -> list[dict[str, Any]]:
        rows = [
            r
            for r in self.snap.meetings
            if (lo := parse_time(r.get('start_time')))
            and (hi := parse_time(r.get('end_time')))
            and lo < end_time
            and hi > start_time
        ]
        return sorted(rows, key=lambda r: parse_time(r['start_time']))[:10]  # type: ignore[arg-type,return-value]

    def meetings(self, uid: Any, start_date: Any = None, end_date: Any = None, limit: int = 50) -> list[dict[str, Any]]:
        rows = [
            r
            for r in self.snap.meetings
            if (at := parse_time(r.get('start_time')))
            and (not start_date or at >= start_date)
            and (not end_date or at <= end_date)
        ]
        return sorted(rows, key=lambda r: parse_time(r['start_time']), reverse=True)[:limit]  # type: ignore[type-var]

    def screen(
        self, uid: Any, start_date: Any = None, end_date: Any = None, limit: int = 400, **kwargs: Any
    ) -> list[dict[str, Any]]:
        return [
            r
            for r in self.snap.screen
            if (not start_date or r['_at'] >= start_date) and (not end_date or r['_at'] <= end_date)
        ][:limit]

    def tasks(self, uid: Any, conversation_id: Any = None, completed: bool = False, limit: int = 30, **kwargs: Any):
        return [
            r
            for r in self.snap.tasks
            if bool(r.get('completed')) == completed
            and (not conversation_id or r.get('conversation_id') == conversation_id)
        ][:limit]

    def conversations(self, uid: Any, limit: int = 60, start_date: Any = None, end_date: Any = None, **kwargs: Any):
        rows = [
            r
            for r in self.snap.conversations.values()
            if not r.get('discarded')
            and (at := self.snap.window(r)[0])
            and (not start_date or at >= start_date)
            and (not end_date or at <= end_date)
        ]
        return sorted(rows, key=lambda r: self.snap.window(r)[0], reverse=True)[:limit]

    def search(self, request: Any) -> dict[str, Any]:
        data = request.model_dump()
        collection, query = data['collections'][0], terms(data.get('query') or '')
        lo, hi = parse_time(data.get('start')), parse_time(data.get('end'))
        person = (data.get('person_ref') or '').partition('/')[2]
        rows = (
            self.snap.memories
            if collection == 'memory_items'
            else self.snap.tasks if collection == 'action_items' else self.snap.conversations.values()
        )
        ranked = []
        for row in rows:
            if row.get('discarded') or row.get('deleted') or row.get('is_locked') or row.get('locked'):
                continue
            if collection == 'conversations':
                at = self.snap.window(row)[0]
                if (lo and (not at or at < lo)) or (hi and (not at or at > hi)):
                    continue
                if person and not any(s.get('person_id') == person for s in row.get('transcript_segments') or []):
                    continue
                structured = row.get('structured') or {}
                text = f"{structured.get('title') or ''}\n{structured.get('overview') or ''}"
            else:
                at = parse_time(row.get('created_at'))
                text = row.get('content') or row.get('description') or row.get('headline') or ''
            hits = score(query, text)
            if query and not hits:
                continue
            ranked.append((hits, at.timestamp() if at else 0, row, text))
        ranked.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
        return {
            'results': [
                {'ref': collection + '/' + str(row.get('id') or index), 'snippet': text[:1200]}
                for index, (_, _, row, text) in enumerate(ranked[: data.get('limit', 6)])
            ]
        }

    # ---- inputs, decision, invoke ----

    def inputs(self, conv: dict[str, Any]) -> tuple[Any, str, int, list[Any], dict[str, Any]]:
        from models.calendar_context import CalendarMeetingContext
        from utils.conversations.meeting_participants import normalize_meeting_participants
        from utils.conversations.relevance_rules import transcript_word_count
        from utils.conversations.transcript_for_llm import render_cluster_transcript
        from utils.llm.conversation_prompt_context import build_conversation_prompt_prefix
        from utils.llm.known_spellings import render_known_spellings, trusted_people_spellings
        from utils.llm.meeting_notes_rich_prompts import NotesFrameImage

        start, end = self.snap.window(conv)
        names = {p['id']: p['name'] for p in self.snap.people if p.get('id') and p.get('name')}
        transcript, speaker_map = render_cluster_transcript(
            conv.get('transcript_segments') or [],
            names=names,
            owner_name=self.snap.owner_name,
            mark_wake_words=True,
        )
        raw = (conv.get('external_data') or {}).get('calendar_meeting_context')
        calendar, context = self.calendar(None, start, end), None
        if raw:
            context = CalendarMeetingContext.model_validate(raw)
        elif calendar:
            first = calendar[0]
            context = CalendarMeetingContext(
                calendar_event_id=str(first.get('calendar_event_id') or first.get('id') or 'snapshot'),
                title=first.get('title') or '',
                participants=[{'name': p} if isinstance(p, str) else p for p in first.get('participants') or []],
                platform=first.get('platform'),
                start_time=parse_time(first['start_time']),
                duration_minutes=max(
                    1, int((parse_time(first['end_time']) - parse_time(first['start_time'])).total_seconds() / 60)
                ),
                calendar_source=first.get('calendar_source') or 'system_calendar',
            )
        meta = self.snap.frames(conv['id'])
        frames = [
            NotesFrameImage(
                frame_id=f['id'], offset_label=offset(start, f.get('captured_at')), data_url=data_url(f['_image'])
            )
            for f in meta
            if f.get('_image')
        ][:4]
        desktop = str(conv.get('source') or '') == 'desktop' and bool(meta or context)
        roster = (
            normalize_meeting_participants(context, conv.get('source'), self.snap.owner_name, (), self.snap.people)
            if context or desktop
            else None
        )
        prefix = build_conversation_prompt_prefix(
            conversation_id=conv['id'],
            transcript=transcript,
            started_at=start,
            timezone_name='America/Los_Angeles',
            language_code=conv.get('language') or 'en',
            calendar_context=context,
            speaker_map=speaker_map,
            roster=roster,
            desktop_meeting_capture=desktop,
            transcript_segment_ids=speaker_map.source_segment_ids,
            known_spellings=render_known_spellings([], trusted_people_spellings(self.snap.people)),
            uid=self.uid,
        )
        if not prefix.shaped_context:
            raise RuntimeError('shaped capture route unavailable')
        words = transcript_word_count(prefix.shaped_context)
        kwargs = dict(
            started_at=start,
            finished_at=end,
            tz='America/Los_Angeles',
            language_code=conv.get('language') or 'en',
            output_language_code='en',
            roster=roster,
            desktop_meeting_capture=desktop,
            existing_action_items=[r['description'] for r in self.tasks(None) if r.get('description')],
            people=self.snap.people,
            capture_sources=tuple((conv.get('capture_group') or {}).get('members') or ()),
            user_corrections=conv.get('user_corrections') or (),
            task_intelligence_capture=False,
        )
        return prefix, prefix.shaped_context, words, frames, kwargs

    def decision(self, cid: str) -> tuple[Any, int]:
        prefix, capture, words, frames, kwargs = self.inputs(self.snap.conversations[cid])
        decision = self.policy.plan_notes_agent(
            uid=self.uid,
            conversation_id=cid,
            words=words,
            has_calendar=kwargs['roster'] is not None,
            has_call_screen=bool(frames) or kwargs['desktop_meeting_capture'],
            capture_sources=len(kwargs['capture_sources']) or 1,
        )
        return decision, words

    def invoke(
        self,
        cid: str,
        gateway: Any = None,
        qualify: bool = False,
        mode: str = 'shadow',
    ) -> dict[str, Any] | None:
        os.environ['NOTES_PACKET_V2_MODE'] = mode
        prefix, capture, words, frames, kwargs = self.inputs(self.snap.conversations[cid])
        self.result, self.error, self.invocation, self.packet_seen, self.raw_calls = None, None, None, None, []
        outer = self

        class _Model:
            def bind(self, **options: Any) -> Any:
                async def ainvoke(messages: list[Any]) -> Any:
                    body = {'model': LANE, 'messages': messages, **options}
                    body.update(body.pop('extra_body', {}))
                    if qualify or gateway is None:
                        raise replay_bench.ControlledStop('qualification', 'sentinel before any request')
                    response = await asyncio.to_thread(gateway.complete, body)
                    message, usage = response['choices'][0]['message'], response.get('usage') or {}
                    calls, invalid = [], []
                    for call in message.get('tool_calls') or []:
                        function = call['function']
                        outer.raw_calls.append((function['name'], function.get('arguments') or '{}'))
                        try:
                            calls.append(
                                {
                                    'id': call['id'],
                                    'name': function['name'],
                                    'args': json.loads(function.get('arguments') or '{}'),
                                }
                            )
                        except (ValueError, TypeError):
                            invalid.append(
                                {'id': call['id'], 'name': function['name'], 'args': function.get('arguments') or ''}
                            )
                    return SimpleNamespace(
                        content=message.get('content') or '',
                        tool_calls=calls,
                        invalid_tool_calls=invalid,
                        usage_metadata={
                            'input_tokens': usage.get('prompt_tokens', 0),
                            'output_tokens': usage.get('completion_tokens', 0),
                            'input_token_details': {
                                'cache_read': (usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0)
                            },
                        },
                    )

                return SimpleNamespace(ainvoke=ainvoke)

        before = {kind: self.agent.REPAIRS.labels(kind=kind)._value.get() for kind in REPAIR_KINDS}
        payload = self.serving.agentic_notes_payload(
            uid=self.uid,
            prefix=prefix,
            model=_Model(),
            capture_evidence=capture,
            words=words,
            frames=frames,
            kwargs=kwargs,
        )
        if qualify:
            if not self.invocation or not isinstance(self.error, replay_bench.ControlledStop):
                raise RuntimeError('qualification transport not reached')
            assert self.invocation['identity'].speaker_names == prefix.speaker_names
            assert self.invocation['contract_v2'] == (mode == 'serve')
            assert self.invocation['transcript_segment_ids'] == prefix.transcript_segment_ids
            assert self.packet_seen.get('version') == (2 if mode == 'serve' else None)
            values = {
                'packet': self.packet_seen,
                'seed': self.invocation['seed'],
                'owner': self.invocation['owner'],
                'schema': self.prompt.tools_for_run(),
                'instructions': self.prompt.instructions_for_run(),
            }
            return {
                'id': cid,
                'words': words,
                'packet_bytes': len(json.dumps(self.packet_seen, default=str).encode()),
                **{
                    key + '_sha256': hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
                    for key, value in values.items()
                },
            }
        if self.error:
            raise self.error
        result = self.result
        if result is None:
            raise RuntimeError('agent not invoked')
        seen, duplicates = set(), 0
        for name, raw in self.raw_calls:
            if name not in self.tools.READ_TOOL_NAMES:
                continue
            try:
                args = json.loads(raw)
                for key in ('query', 'person'):
                    if isinstance(args.get(key), str):
                        args[key] = ' '.join(args[key].split()).casefold()
                if isinstance(args.get('names'), list):
                    args['names'] = sorted(
                        set(' '.join(n.split()).casefold() for n in args['names'] if isinstance(n, str))
                    )
                if name in ('get_calendar', 'get_screen_activity'):
                    defaults: dict[str, Any] = {'start': None, 'end': None}
                    if name == 'get_screen_activity':
                        defaults['query'] = ''
                        defaults['limit'] = 25
                    args = {k: v for k, v in args.items() if k not in defaults or v not in (defaults[k], '')}
                key = name + json.dumps(args, sort_keys=True)
            except (ValueError, TypeError, AttributeError):
                continue
            duplicates += key in seen
            seen.add(key)
        identity = (self.invocation or {}).get('identity')
        invariant_failures = invariants.label_free_invariants(
            payload,
            stop=result.stop,
            transcript_words=words,
            est_cost_usd=result.cost_usd,
            cost_cap_usd=self.policy.MAX_COST_USD,
        ) + invariants.identity_invariants(payload, identity)
        case_result = None
        if cid in self.cases:
            case_result = invariants.score_case(
                self.cases[cid], payload, identity, invariant_failures=invariant_failures
            )
        repairs = {kind: self.agent.REPAIRS.labels(kind=kind)._value.get() - before[kind] for kind in REPAIR_KINDS}
        return {
            'id': cid,
            'words': words,
            'tier': tier(words),
            'forced': result.forced,
            'reason': result.force_reason,
            'stop': result.stop,
            'submitted': payload is not None,
            'lookups': result.tool_calls,
            'tools': dict(result.tools),
            'duplicates': duplicates,
            'cached_lookups': result.duplicate_lookups,
            'refused_lookups': result.refused_lookups,
            'rejections': len(result.rejections),
            'rejections_by_kind': {k: v for k, v in repairs.items() if k.startswith('rejected_')},
            'repairs_by_kind': {k: v for k, v in repairs.items() if not k.startswith('rejected_')},
            'cost': result.cost_usd,
            'prompt_tokens': result.prompt_tokens,
            'cached_tokens': result.cached_tokens,
            'completion_tokens': result.completion_tokens,
            'cache_ratio': result.cache_ratio,
            'turns': result.turns,
            'latency_seconds': result.latency_seconds,
            'packet_bytes': len(json.dumps(self.packet_seen or {}, default=str).encode()),
            'invariant_failures': invariant_failures,
            'case': case_result,
        }

    # ---- replay_bench.ReplayAdapter ----

    def case_ids(self) -> list[str]:
        selection = replay_bench.read_json(Path(os.environ[replay_bench.SELECTION_ENV]), {})
        return [str(case) for case in selection.get('ids') or []]

    def run_case(self, case_id: str, transport: Any) -> dict[str, Any]:
        return self.invoke(case_id, gateway=transport)  # type: ignore[return-value]

    def first_request(self, case_id: str) -> dict[str, Any]:
        captured: dict[str, Any] = {}

        class _Capture:
            def complete(self, body: dict[str, Any]) -> dict[str, Any]:
                captured['body'] = body
                raise replay_bench.ControlledStop('qualification', 'first request captured before send')

        try:
            self.invoke(case_id, gateway=_Capture())
        except replay_bench.ControlledStop:
            pass
        if 'body' not in captured:
            raise RuntimeError('first request not reached')
        return captured['body']

    # ---- optional hooks ----

    def select(self, selection_path: Path) -> None:
        buckets: dict[str, list[str]] = {key: [] for key in ('short', 'medium', 'long')}
        for cid, conv in sorted(self.snap.conversations.items()):
            if conv.get('discarded'):
                continue
            decision, words = self.decision(cid)
            if decision.run:
                buckets[tier(words)].append(cid)
        if any(not bucket for bucket in buckets.values()) or sum(map(len, buckets.values())) < 20:
            raise RuntimeError('insufficient eligible tier coverage')
        ids = sum((buckets[key][:count] for key, count in (('short', 7), ('medium', 7), ('long', 6))), [])
        ids += sorted(set(sum(buckets.values(), [])) - set(ids))[: max(0, 20 - len(ids))]
        labelled, excluded = [], []
        for cid in self.cases:
            reason = (
                'not_in_snapshot'
                if cid not in self.snap.conversations
                else 'ineligible' if not self.decision(cid)[0].run else None
            )
            if reason:
                excluded.append({'id': cid, 'reason': reason})
            else:
                labelled.append(cid)
        replay_bench.write_json(
            selection_path,
            {
                'bench_ids': ids,
                'labelled_ids': labelled,
                'ids': list(dict.fromkeys(ids + labelled)),
                'n': int(os.environ.get('OWNER_LAB_REPEATS') or 2),
                'available_tiers': {key: len(value) for key, value in buckets.items()},
                'labelled_excluded': excluded,
            },
        )

    def qualify(self) -> None:
        from config.refactor_modes import mode as mode_of, serving_for

        pinned = 'NOTES_PACKET_V2_MODE'
        assert mode_of(pinned, environ={}) == mode_of(pinned, environ=dict(PINNED_DEFAULTS)) == 'shadow'
        unset = serving_for(pinned, 'bench-owner', environ={})
        pinned_serving = serving_for(pinned, 'bench-owner', environ=dict(PINNED_DEFAULTS))
        assert unset is False and pinned_serving is False
        selection = replay_bench.read_json(Path(os.environ[replay_bench.SELECTION_ENV]), {})
        records = [self.invoke(cid, qualify=True) for cid in selection['ids']]
        self.invoke(selection['ids'][0], qualify=True, mode='serve')
        cid = selection['ids'][0]
        prefix, _, _, frames, kwargs = self.inputs(self.snap.conversations[cid])
        box = self.tools.NotesToolbox(
            uid=self.uid,
            conversation_id=cid,
            started_at=kwargs['started_at'],
            finished_at=kwargs['finished_at'],
            frames=frames,
        )

        async def sources() -> None:
            screen = await box.get_screen_activity()
            assert screen == await box.get_screen_activity(
                start=kwargs['started_at'].isoformat(), end=kwargs['finished_at'].isoformat()
            )
            if hasattr(self.tools, 'screen_result'):
                assert screen == self.tools.screen_result(
                    self.screen(None, kwargs['started_at'], kwargs['finished_at'])
                )
            assert await box.get_calendar() == {
                'meetings': [
                    self.tools.calendar_row(row)
                    for row in self.calendar(None, kwargs['started_at'], kwargs['finished_at'])
                ]
            }
            original = self.tools.screen_activity_db.get_screen_activity
            self.tools.screen_activity_db.get_screen_activity = lambda *args, **named: [
                {'appName': 'Slack', 'ocrText': 'BENCH_PRIVATE_SENTINEL', 'timestamp': FIXED_NOW}
            ]
            private = await box.get_screen_activity()
            assert 'BENCH_PRIVATE_SENTINEL' not in json.dumps(private, default=str)
            self.tools.screen_activity_db.get_screen_activity = original

        asyncio.run(sources())
        from utils.llm.notes_identity import NotesIdentity

        assert not NotesIdentity(meeting_names=('Bench Person',)).supported('Bench Person', 'spk_1')
        assert NotesIdentity(speaker_names=(('spk_1', 'Bench Person'),)).supported('Bench Person', 'spk_1')
        out = (
            Path(os.environ[replay_bench.SELECTION_ENV]).parent
            / f"qualification-{os.environ.get('OWNER_LAB_ARM', 'arm')}.json"
        )
        replay_bench.write_json(out, records)


if __name__ == '__main__':  # pragma: no cover - manual smoke entry
    sys.exit('run through testing.owner_lab.replay_bench')
