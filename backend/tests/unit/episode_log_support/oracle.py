"""Oracle harness: drive TODAY'S attach path over StrictFirestore (unit-test double).

Mirrors how backend/tests/unit/test_recorded_span.py drives
episode_timeline.attach_recorded: same fixture, same choose policy, same
candidates monkeypatch (in-memory range query with production semantics).
Discard and donor-repoint use the production update_episode code path.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from database import episode_timeline, episodes, episode_log
from utils.episodes import timeline
from utils.conversations.recorded_time import write_span
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


class Oracle:
    """Context manager: patches seal/unseal/candidates for its lifetime."""

    def __init__(self, uid: str = 'proto-u'):
        self.uid = uid
        self.store = StrictFirestore()
        self.events: list[str] = []
        self._saved: dict[tuple[str, str], Any] = {}

    # ------------------------------------------------------------ lifecycle
    def __enter__(self) -> 'Oracle':
        store, uid = self.store, self.uid
        self._saved[('episode_log', 'fact_page')] = episode_log.fact_page
        episode_log.fact_page = lambda u, after, through, limit=64, **kwargs: sorted(
            [
                v
                for k, v in store.rows.items()
                if k[:3] == ('users', u, 'episode_facts') and after < v['seq'] <= through
            ],
            key=lambda v: v['seq'],
        )[:limit]
        self._saved[('episode_timeline', 'recorded_candidates')] = episode_timeline.recorded_candidates
        self._saved[('episodes', 'seal')] = episodes.seal
        self._saved[('episodes', 'unseal')] = episodes.unseal

        def candidates(u, started, finished, *, firestore_client=None, transaction=None):
            from config.recorded_time_tolerances import CLOSE_GAP_SECONDS, MAX_EPISODE_SECONDS

            lo = started - timedelta(seconds=MAX_EPISODE_SECONDS + CLOSE_GAP_SECONDS)
            hi = finished + timedelta(seconds=CLOSE_GAP_SECONDS)
            rows = [
                dict(v, id=k[-1])
                for k, v in sorted(store.rows.items())
                if k[:2] == ('users', uid)
                and k[2] == 'episodes'
                and isinstance(v.get('started_at'), type(lo))
                and lo <= v['started_at'] <= hi
            ]
            rows.sort(key=lambda r: (r['started_at'], r['id']))
            if len(rows) >= episode_timeline.PAGE_LIMIT:
                raise episodes.EpisodeConflict('recorded_window_incomplete')
            return [r for r in rows if not r.get('recorded_merged_into')]

        episode_timeline.recorded_candidates = candidates
        episodes.seal = lambda u, row: dict(row)
        episodes.unseal = lambda u, row: dict(row) if row is not None else None
        return self

    def __exit__(self, *exc) -> None:
        episode_log.fact_page = self._saved[('episode_log', 'fact_page')]
        episode_timeline.recorded_candidates = self._saved[('episode_timeline', 'recorded_candidates')]
        episodes.seal = self._saved[('episodes', 'seal')]
        episodes.unseal = self._saved[('episodes', 'unseal')]

    # ---------------------------------------------------------------- ops
    def conversation(self, cid: str, start, end) -> None:
        """Conversation row with recorded clocks, as sync intake writes it."""
        self.store.rows[('users', self.uid, 'conversations', cid)] = dict(
            id=cid, **write_span(dict(started_at=start, finished_at=end), arrival_at=end)
        )

    def attach(self, cid: str, start, end, source: str | None = 'omi') -> Any:
        self.conversation(cid, start, end)
        result = episode_timeline.attach_recorded(
            self.uid,
            cid,
            source,
            start,
            end,
            choose=timeline.choose_recorded_episode,
            new_episode={},
            firestore_client=self.store,
        )
        self.events.append(f'attach {cid} [{start.strftime("%H:%M:%S")}..{end.strftime("%H:%M:%S")}]')
        return result

    def discard(self, cid: str) -> None:
        owner = episodes.get_episode_for_conversation(self.uid, cid, firestore_client=self.store)
        if not owner:
            self.events.append(f'discard {cid}: no owner')
            return
        episodes.update_episode(
            self.uid,
            str(owner['id']),
            expected_version=int(owner.get('state_version') or 0),
            updates={
                'discarded_conversation_ids': [*(owner.get('discarded_conversation_ids') or []), cid],
            },
            firestore_client=self.store,
        )
        self.events.append(f'discard {cid} on {owner["id"]}')

    def repoint(self, donor: str, survivor: str) -> None:
        """_repoint_absorbed placement core (repointed_members + member swap)."""
        owner = episodes.get_episode_for_conversation(self.uid, donor, firestore_client=self.store)
        if not owner or donor not in (owner.get('conversation_ids') or []):
            self.events.append(f'repoint {donor}->{survivor}: donor not a member')
            return
        updates = {
            **episode_timeline.repointed_members(owner, donor, survivor),
            'conversation_ids': list(dict.fromkeys(survivor if d == donor else d for d in owner['conversation_ids'])),
            'primary_conversation_id': (
                survivor if owner.get('primary_conversation_id') == donor else owner.get('primary_conversation_id')
            ),
        }
        episodes.update_episode(
            self.uid,
            str(owner['id']),
            expected_version=int(owner.get('state_version') or 0),
            updates=updates,
            link_conversation_ids=[survivor],
            firestore_client=self.store,
        )
        # The donor conversation is absorbed (sync_merged_into) and hidden;
        # production never rewrites its link. Drop it from the membership view.
        self.store.rows.pop(('users', self.uid, 'episode_links', donor), None)
        self.events.append(f'repoint {donor}->{survivor} on {owner["id"]}')

    # ------------------------------------------------------------ snapshot
    def _episodes(self) -> dict[str, dict]:
        return {
            k[-1]: dict(v) for k, v in self.store.rows.items() if k[:2] == ('users', self.uid) and k[2] == 'episodes'
        }

    def snapshot(self) -> dict:
        rows = self._episodes()
        windows = []
        redirects = {}
        for eid, row in rows.items():
            if row.get('recorded_merged_into'):
                redirects[eid] = row['recorded_merged_into']
                continue
            members = row.get('recorded_members') or {}
            windows.append(
                {
                    'id': eid,
                    'started_at': row['started_at'],
                    'last_activity_at': row['last_activity_at'],
                    'close_reason': row.get('close_reason'),
                    'conversation_ids': sorted(row.get('conversation_ids') or []),
                    'member_activity': row.get('member_activity') or {},
                    'recorded_members': {cid: (f['start'], f['end'], f.get('source')) for cid, f in members.items()},
                    'sources': row.get('sources') or [],
                    'discarded_conversation_ids': sorted(row.get('discarded_conversation_ids') or []),
                    'state_version': row.get('state_version'),
                }
            )
        windows.sort(key=lambda w: (w['started_at'], w['id']))
        membership = {}
        for k, v in self.store.rows.items():
            if (
                k[:2] == ('users', self.uid)
                and k[2] == 'episode_links'
                and k[3] not in {'current', 'last_closed', 'recorded_timeline'}
            ):
                if v.get('episode_id'):
                    membership[k[3]] = v['episode_id']
        return {
            'windows': windows,
            'redirects': redirects,
            'membership': membership,
            'events': list(self.events),
        }

    def writes(self) -> int:
        """Rough transactional write count (sets+updates across transactions)."""
        return sum(len(t.sets) + len(t.updates) + len(t.creates) for t in self.store.transactions)
