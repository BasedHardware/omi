"""The ``fake`` chain engine: the lab's own plumbing with a stand-in for the product.

``run --engine fake`` swaps the product finalizer and the emulator-backed store for small
in-memory ones, so a run proves the lab end to end without a Firestore emulator: ordered
driver, frozen clock, LLM calls through the real proxy (keyed, priced, capped, attributed
by header), would-have-fired pushes, export, day file, baseline and the inspector. It says
nothing about product fidelity; that is the ``product`` engine on the local stack.

Per conversation the stand-in makes one ``notes`` call (title, overview, discard, tasks,
memories) through the proxy; per day one ``daily_summary`` call. Everything is labelled
``engine: fake`` in ``chain.json``.
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from testing.pipeline_lab.chain.barrier import ExecutorBarrier
from testing.pipeline_lab.chain.driver import ChainDriver
from testing.pipeline_lab.chain.order import plan_chain
from testing.pipeline_lab.day.outputs import build_day_json, recap_instant
from testing.pipeline_lab.llm_proxy.tagging import CONVERSATION_HEADER, STAGE_HEADER
from testing.pipeline_lab.sinks.capture import CaptureSinks, capture_scope
from testing.pipeline_lab.stack.clock import LabClock
from testing.pipeline_lab.stack.io import iso, write_json
from testing.pipeline_lab.store import read_jsonl

NOTES_SCHEMA = {
    'type': 'object',
    'properties': {
        'discarded': {'type': 'boolean'},
        'title': {'type': 'string'},
        'overview': {'type': 'string'},
        'emoji': {'type': 'string'},
        'category': {'type': 'string'},
        'action_items': {'type': 'array', 'items': {'type': 'string'}},
        'memories': {'type': 'array', 'items': {'type': 'string'}},
    },
}
SUMMARY_SCHEMA = {
    'type': 'object',
    'properties': {
        'headline': {'type': 'string'},
        'overview': {'type': 'string'},
        'highlights': {'type': 'array', 'items': {'type': 'string'}},
    },
}


def _wait_for_logged_call(call_log: Path, call_id: str | None) -> None:
    if not call_id:
        raise RuntimeError('fake chain proxy response is missing its LLM call ID')
    deadline = time.monotonic() + 5
    while not any(row.get('id') == call_id for row in read_jsonl(call_log)):
        if time.monotonic() >= deadline:
            raise TimeoutError('fake chain proxy call did not reach the log before export')
        time.sleep(0.01)


def ask(
    proxy_url: str,
    *,
    stage: str,
    conversation_id: Optional[str],
    prompt: str,
    schema: dict,
    call_log: Path | None = None,
) -> dict[str, Any]:
    """One structured chat call through the lab proxy, tagged for attribution."""
    body = {
        'model': 'lab-fake-model',
        'messages': [
            {'role': 'system', 'content': f'pipeline lab fake engine: {stage}'},
            {'role': 'user', 'content': prompt},
        ],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': stage, 'schema': schema}},
    }
    headers = {'Content-Type': 'application/json', 'X-Omi-LLM-Feature': f'pipeline_lab_fake_{stage}'}
    headers[STAGE_HEADER] = stage
    if conversation_id:
        headers[CONVERSATION_HEADER] = conversation_id
    request = urllib.request.Request(
        proxy_url.rstrip('/') + '/v1/chat/completions', data=json.dumps(body).encode(), headers=headers, method='POST'
    )
    # No ambient HTTP proxy: the request carries private transcript text and must reach the loopback lab proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=60) as response:  # noqa: S310 - loopback proxy only
        payload = json.loads(response.read())
        call_id = response.headers.get('X-Pipeline-Lab-Call-Id')
    if call_log is not None:
        # The response can arrive while the proxy is still recording this call.
        _wait_for_logged_call(call_log, call_id)
    return json.loads(payload['choices'][0]['message']['content'] or '{}')


class FakeChainStore:
    """In-memory stand-in for the emulator-backed ``ProductChainStore``."""

    def __init__(self, people: Mapping[str, str] | None = None):
        self.rows: dict[str, dict[str, Any]] = {}
        self.action_items: dict[str, list[dict[str, Any]]] = {}
        self.memories: dict[str, list[dict[str, Any]]] = {}
        self.people = dict(people or {})

    def seed_conversation(self, uid: str, row: Mapping[str, Any]) -> None:
        self.rows[str(row['id'])] = {**row, 'uid': uid}

    def read_conversation(self, uid: str, conversation_id: str) -> dict[str, Any] | None:
        return self.rows.get(conversation_id)

    def action_items_for(self, uid: str, conversation_id: str) -> list[dict[str, Any]]:
        return list(self.action_items.get(conversation_id, []))

    def memories_for(self, uid: str, conversation_id: str) -> list[dict[str, Any]]:
        return list(self.memories.get(conversation_id, []))

    def people_names(self, uid: str) -> dict[str, str]:
        return dict(self.people)


class FakeFinalizer:
    def __init__(self, store: FakeChainStore, sinks: CaptureSinks, proxy_url: str, clock: LabClock, call_log: Path):
        self.store, self.sinks, self.proxy_url, self.clock = store, sinks, proxy_url, clock
        self.call_log = call_log

    async def finalize(self, uid: str, conversation_id: str, language: str | None) -> str:
        import asyncio

        row = self.store.rows[conversation_id]
        transcript = ' '.join(str(s.get('text') or '') for s in row.get('transcript_segments') or [])
        if not transcript.strip():
            row.update(discarded=True, discard_reason='empty transcript', status='completed')
            return 'completed'
        notes = await asyncio.to_thread(
            ask,
            self.proxy_url,
            stage='notes',
            conversation_id=conversation_id,
            prompt=transcript,
            schema=NOTES_SCHEMA,
            call_log=self.call_log,
        )
        row['status'] = 'completed'
        row['discarded'] = bool(notes.get('discarded'))
        row['structured'] = {k: notes.get(k) or '' for k in ('title', 'overview', 'emoji', 'category')}
        row['structured']['events'] = []
        if row['discarded']:
            return 'completed'
        now = iso(self.clock.now())
        tasks = [str(t) for t in notes.get('action_items') or [] if str(t).strip()]
        self.store.action_items[conversation_id] = [
            {'description': t, 'completed': False, 'conversation_id': conversation_id, 'created_at': now} for t in tasks
        ]
        self.store.memories[conversation_id] = [
            {'content': str(m), 'category': 'interesting', 'conversation_id': conversation_id, 'created_at': now}
            for m in notes.get('memories') or []
            if str(m).strip()
        ]
        if tasks:
            with capture_scope(conversation_id, 'tasks'):
                self.sinks.record_messages(
                    [{'notification': {'title': 'New task', 'body': tasks[0]}, 'data': {'type': 'action_item'}}],
                    api='fake_engine',
                )
        return 'completed'


async def replay_chain_fake(
    *,
    run_dir: Path,
    uid: str,
    day: str,
    tz_name: str,
    day_start: Any,
    conversations: Sequence[Mapping[str, Any]],
    start_state: Any,
    proxy_url: str,
    production_recap_at: Any = None,
) -> dict[str, Any]:
    clock = LabClock(day_start)
    sinks = CaptureSinks(run_dir=run_dir, clock=clock.now)
    people = {str(p.get('id')): str(p.get('name') or '') for p in getattr(start_state, 'people', []) if p.get('id')}
    store = FakeChainStore(people)
    driver = ChainDriver(
        uid=uid,
        store=store,
        finalizer=FakeFinalizer(store, sinks, proxy_url, clock, Path(run_dir) / 'llm_calls.jsonl'),
        clock=clock,
        barrier=ExecutorBarrier(),
        sinks=sinks,
        run_dir=run_dir,
    )
    report = await driver.run(plan_chain(conversations))
    at, source = recap_instant(day, tz_name, production_at=production_recap_at)
    clock.set(at)
    kept = [row for cid, row in store.rows.items() if not row.get('discarded')]
    digest = '\n'.join(str((row.get('structured') or {}).get('title') or '') for row in kept)
    import asyncio

    summary = await asyncio.to_thread(
        ask, proxy_url, stage='daily_summary', conversation_id=None, prompt=digest or 'quiet day', schema=SUMMARY_SCHEMA
    )
    memories_after = list(getattr(start_state, 'memories', [])) + [m for rows in store.memories.values() for m in rows]
    payload = build_day_json(
        daily_summary={**summary, 'date': day},
        goals=getattr(start_state, 'goals', []),
        goals_before=getattr(start_state, 'goals', []),
        memories_before=getattr(start_state, 'memories', []),
        memories_after=memories_after,
        notifications=sinks.notifications,
        chat_index={'checked': False, 'reason': 'fake engine has no vector index'},
        recap={'at': iso(at), 'at_source': source, 'status': 'ok', 'engine': 'fake'},
    )
    write_json(Path(run_dir) / 'day.json', payload)
    chain = report.as_dict()
    chain['engine'] = 'fake'
    write_json(Path(run_dir) / 'chain.json', chain)
    return {'chain': chain, 'notifications': len(sinks.notifications), 'engine': 'fake'}
