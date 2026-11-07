"""Arrival-ordered pure projector: replay an append-only fact log into the episode view.

Classes of episode in the view (mirroring production semantics):
- ``pure``   windows straight from database.episode_recorded_components.partition()
             over folded envelopes — the claim under test.
- ``grown``  automatic windows that today's _attach_recorded_window extended in
             place (fence-blocked intake whose choose() selected the automatic
             window, or fence-adjacent components that live on the window path
             forever). Member envelopes stay foldable; the shape is an override.
- ``fence``  non-automatic episodes: live/user/calendar (passed in), discard-
             frozen windows, and wedge episodes born from the fallback path
             (which carry no recorded_members and never re-partition).

Blocked-intake detection mirrors episode_recorded_components.attach's bail
(choose(fixed, s, e) or choose(fixed, s, s) non-None, a non-automatic link
owner, or a fixed row connected to the expanded component), and the fallback
selection mirrors episode_timeline._attach_recorded_window: choose(all, s, s),
member owner first, else create the `recorded-episode:` wedge.
Replay is a left fold: view(N) is a pure function of the first N facts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid5

from config.recorded_time_tolerances import CLOSE_GAP_SECONDS, MAX_EPISODE_SECONDS
from database.episode_recorded_components import partition
from utils.episodes.timeline import choose_recorded_episode


def _iso(value: str):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _envelope_merge(old: dict | None, start, end, source: str | None) -> dict:
    return {
        'start': min(old['start'], start) if old else start,
        'end': max(old['end'], end) if old else end,
        'source': source or (old or {}).get('source'),
    }


def _connected(a_lo, a_hi, b_lo, b_hi) -> bool:
    return max(0.0, (a_lo - b_hi).total_seconds(), (b_lo - a_hi).total_seconds()) < CLOSE_GAP_SECONDS


def _group_envelope(items: dict[str, dict], cid: str) -> tuple[set[str], dict]:
    """CLOSE_GAP-connected group of ``cid`` and its envelope (partition grouping)."""
    group = {cid}
    frontier = [cid]
    while frontier:
        cur = frontier.pop()
        f = items[cur]
        for other, g in items.items():
            if other in group:
                continue
            if _connected(f['start'], f['end'], g['start'], g['end']):
                group.add(other)
                frontier.append(other)
    return group, {
        'start': min(items[c]['start'] for c in group),
        'end': max(items[c]['end'] for c in group),
    }


class ProjectedEpisode:
    """Window or fence state; extend() mirrors _attach_recorded_window."""

    def __init__(
        self,
        *,
        id,
        started_at,
        last_activity_at,
        close_reason,
        status='closed',
        recorded_members=None,
        conversation_ids=None,
        discarded=(),
        recorded_end=None,
        fixed: bool,
        member_activity=None,
    ):
        self.id = id
        self.started_at = started_at
        self.last_activity_at = last_activity_at
        self.recorded_end = recorded_end or last_activity_at
        self.close_reason = close_reason
        self.status = status
        self.recorded_members: dict[str, dict] = dict(recorded_members or {})
        self.conversation_ids: list[str] = list(conversation_ids or self.recorded_members)
        self.member_activity: dict[str, Any] = dict(member_activity or {})
        self.discarded_conversation_ids = list(discarded)
        self.fixed = fixed  # fences never re-partition
        self.applied_members = frozenset(self.conversation_ids)
        self.applied_discards = tuple(self.discarded_conversation_ids)

    def row(self) -> dict:
        explicit = self.status == 'closed' and self.close_reason not in {'gap', 'idle'}
        return {
            'id': self.id,
            'started_at': self.started_at,
            'last_activity_at': self.last_activity_at,
            'recorded_end': self.recorded_end if explicit else self.last_activity_at,
            'closed_at': self.recorded_end,
            'status': self.status,
            'close_reason': self.close_reason,
        }

    def window(self) -> dict:
        return {
            'id': self.id,
            'started_at': self.started_at,
            'last_activity_at': self.last_activity_at,
            'close_reason': self.close_reason,
            'conversation_ids': sorted(self.conversation_ids),
            'member_activity': dict(self.member_activity),
            'recorded_members': {cid: dict(f) for cid, f in self.recorded_members.items()},
            'sources': sorted({f['source'] for f in self.recorded_members.values() if f.get('source')}),
            'discarded_conversation_ids': sorted(self.discarded_conversation_ids),
            'fixed': self.fixed,
        }

    def extend(self, cid: str, start, end, source, all_starts: list) -> str:
        if start >= self.started_at + timedelta(seconds=MAX_EPISODE_SECONDS):
            return 'beyond_cap'
        lo = min(self.started_at, start)
        window_end = min(end, lo + timedelta(seconds=MAX_EPISODE_SECONDS))
        if self.status != 'live' and self.close_reason not in {'gap', 'idle'}:
            window_end = min(window_end, self.recorded_end)
        if self.status == 'live' or self.close_reason in {'gap', 'idle'}:
            following = [s for s in all_starts if s > lo and s != self.started_at]
            if following:
                window_end = min(window_end, min(following))
        if window_end < start or (window_end == start and end > start):
            return 'no_progress'
        if cid not in self.conversation_ids:
            self.conversation_ids.append(cid)
        self.started_at = lo
        self.last_activity_at = max(self.last_activity_at, window_end)
        self.member_activity[cid] = window_end
        self.recorded_members[cid] = _envelope_merge(self.recorded_members.get(cid), start, end, source)
        if window_end < end and self.close_reason in {'gap', 'idle'}:
            self.close_reason = 'hard_cap' if window_end == lo + timedelta(seconds=MAX_EPISODE_SECONDS) else 'boundary'
        if self.status != 'live':
            self.recorded_end = self.last_activity_at
        if self.close_reason == 'boundary':
            self.fixed = True
        self.apply_retained_bounds_if_changed()
        return 'attached'

    def _retained_changed(self) -> bool:
        """episodes.retained_bounds_changed: discards added, or any discards
        plus a changed member set (extend/repoint mutate conversation_ids)."""
        if tuple(self.discarded_conversation_ids) != self.applied_discards:
            return True
        if self.discarded_conversation_ids and frozenset(self.conversation_ids) != self.applied_members:
            return True
        return False

    def apply_retained_bounds_if_changed(self) -> None:
        if self._retained_changed():
            self.apply_retained_bounds()
        self.applied_members = frozenset(self.conversation_ids)
        self.applied_discards = tuple(self.discarded_conversation_ids)

    def apply_retained_bounds(self) -> None:
        """database.episodes.retained_bounds on a discard CAS: bounds rebuild
        from non-discarded members' evidence (conversation recorded clocks ==
        our envelopes); a fully-discarded window degenerates to its start."""
        hidden = set(self.discarded_conversation_ids)
        kept = {c: f for c, f in self.recorded_members.items() if c not in hidden}
        if kept:
            self.started_at = min(f['start'] for f in kept.values())
            self.last_activity_at = max(self.started_at, max(f['end'] for f in kept.values()))
            self.member_activity = {c: f['end'] for c, f in kept.items()}
        else:
            self.last_activity_at = self.started_at
            self.member_activity = {}
        if self.status == 'closed':
            self.recorded_end = self.last_activity_at


class Projector:
    def __init__(self, uid: str, fixed_episodes: Iterable[dict] = ()):
        self.uid = uid
        self.spans: dict[str, dict] = {}  # envelopes of the automatic domain
        self.episodes: list[ProjectedEpisode] = []  # grown overrides + fences
        for row in fixed_episodes:
            self.episodes.append(
                ProjectedEpisode(
                    id=row['id'],
                    started_at=row['started_at'],
                    last_activity_at=row.get('last_activity_at'),
                    close_reason=row.get('close_reason'),
                    status=row.get('status', 'closed'),
                    recorded_members=row.get('recorded_members'),
                    conversation_ids=row.get('conversation_ids'),
                    recorded_end=row.get('recorded_end'),
                    member_activity=row.get('member_activity'),
                    fixed=True,
                )
            )
        self.windows: list[ProjectedEpisode] = []  # pure partition output
        self.redirects: dict[str, str] = {}
        self.cid_redirect: dict[str, str] = {}
        self.events: list[str] = []
        self._previous_rows: list[dict] | None = None
        self.issued_ids: set[str] = set()  # every window id ever live (incl. tombstones)

    # ------------------------------------------------------------------ utils
    def _resolve(self, cid: str) -> str:
        seen = set()
        while cid in self.cid_redirect and cid not in seen:
            seen.add(cid)
            cid = self.cid_redirect[cid]
        return cid

    def _find(self, cid: str) -> ProjectedEpisode | None:
        for ep in [*self.episodes, *self.windows]:
            if cid in ep.conversation_ids:
                return ep
        return None

    def _all_starts(self, exclude=None) -> list:
        return [e.started_at for e in [*self.episodes, *self.windows] if e is not exclude]

    def _view_rows(self) -> list[dict]:
        return [e.row() for e in [*self.episodes, *self.windows]]

    def _fences(self) -> list[ProjectedEpisode]:
        return [e for e in [*self.episodes, *self.windows] if e.fixed]

    def _settle_id(self, window: dict, carried: set[str]) -> None:
        """episode_recorded_components.attach displaced-id rule: never reuse an
        occupied id (live row or redirect tombstone) for a window that is not
        the very row being repartitioned."""
        for attempt in range(128):
            if window['id'] not in self.issued_ids or window['id'] in carried:
                return
            window['id'] = str(
                uuid5(
                    NAMESPACE_URL,
                    f"recorded-window-displaced:{self.uid}:{window['started_at'].isoformat()}:{attempt}",
                )
            )
        raise RuntimeError('recorded_window_id_exhausted')

    # -------------------------------------------------------------- partition
    def _recompute(self) -> None:
        frozen = [ep for ep in self.windows if ep.fixed]
        self.windows = [ep for ep in self.windows if not ep.fixed]
        self.episodes.extend(ep for ep in frozen if ep not in self.episodes)
        overridden = {cid for ep in self.episodes for cid in ep.conversation_ids}
        free = {cid: dict(f) for cid, f in self.spans.items() if cid not in overridden}
        previous_ids = {e.id for e in [*self.windows, *self.episodes]}
        previous = {r['id']: r for r in (self._previous_rows or [])}
        carried = {e.id for e in self.windows}  # untouched components keep their ids
        produced = partition(self.uid, free)
        for window in produced:
            self._settle_id(window, carried)
        new_ids = {w['id'] for w in produced}
        self.issued_ids |= new_ids
        new_windows = [
            ProjectedEpisode(
                id=w['id'],
                started_at=w['started_at'],
                last_activity_at=w['last_activity_at'],
                close_reason=w['close_reason'],
                recorded_members={c: dict(self.spans[c]) for c in w['conversation_ids']},
                conversation_ids=w['conversation_ids'],
                fixed=False,
                member_activity={c: min(self.spans[c]['end'], w['last_activity_at']) for c in w['conversation_ids']},
            )
            for w in produced
        ]
        current_ids = {e.id for e in [*new_windows, *self.episodes]}
        for gone in previous_ids - current_ids:
            row = previous.get(gone)
            if row is None:
                continue
            owner = next(
                (e for e in [*new_windows, *self.episodes] if e.started_at <= row['started_at'] < e.last_activity_at),
                None,
            )
            target = owner or (new_windows[-1] if new_windows else (self.episodes[-1] if self.episodes else None))
            if target is not None:
                self.redirects[gone] = target.id
        self.windows = new_windows
        self._previous_rows = None

    # ------------------------------------------------------------------ folds
    def record_span(self, cid: str, start, end, source: str | None) -> None:
        cid = self._resolve(cid)
        owner = self._find(cid)
        fences = self._fences()
        fence_rows = [e.row() for e in fences]
        blocked = choose_recorded_episode(fence_rows, start, end) or choose_recorded_episode(fence_rows, start, start)
        touched = {**self.spans, cid: _envelope_merge(self.spans.get(cid), start, end, source)}
        _, envelope = _group_envelope(touched, cid)
        fence_connected = any(
            _connected(envelope['start'], envelope['end'], e.started_at, e.last_activity_at) for e in fences
        )
        if owner is None or not owner.fixed:
            if blocked is None and not fence_connected:
                # Canonical path: linked owner automatic (or none) and no fixed
                # boundary owns intake -> repartition the merged component.
                group, _ = _group_envelope(touched, cid)
                for ep in [e for e in self.episodes if not e.fixed]:
                    if set(ep.conversation_ids) & group:
                        self._previous_rows = self._previous_rows or self._view_rows()
                        self.episodes.remove(ep)
                self.spans[cid] = _envelope_merge(self.spans.get(cid), start, end, source)
                self._previous_rows = self._previous_rows or self._view_rows()
                self._recompute()
                self.events.append(f'span {cid}: partition -> {len(self.windows)} pure windows')
                return
            if owner is not None:
                # Blocked with an automatic linked owner: the window path extends it.
                outcome = owner.extend(cid, start, end, source, self._all_starts(owner))
                self.spans[cid] = _envelope_merge(self.spans.get(cid), start, end, source)
                self.events.append(f'span {cid}: owner-extend {owner.id} -> {outcome}')
                return
        else:
            outcome = owner.extend(cid, start, end, source, self._all_starts(owner))
            self.events.append(f'span {cid}: member-extend {owner.id} -> {outcome}')
            return
        # Fence-blocked with no owner: the fallback window path. Selection is
        # choose(all, s, s); a selected window grows in place, else wedge-create.
        selected = choose_recorded_episode(self._view_rows(), start, start)
        if selected is not None:
            target = next(e for e in [*self.episodes, *self.windows] if e.id == selected['id'])
            outcome = target.extend(cid, start, end, source, self._all_starts(target))
            if not target.fixed:
                self.spans[cid] = _envelope_merge(self.spans.get(cid), start, end, source)
            self.events.append(f'span {cid}: {"fence" if target.fixed else "window"}-extend {target.id} -> {outcome}')
            return
        # Wedge create: episode_timeline._attach_recorded_window else-branch.
        following = [s for s in self._all_starts() if s > start]
        window_end = min(end, start + timedelta(seconds=MAX_EPISODE_SECONDS))
        if following:
            window_end = min(window_end, min(following))
        close_reason = (
            ('hard_cap' if window_end == start + timedelta(seconds=MAX_EPISODE_SECONDS) else 'boundary')
            if window_end < end
            else 'gap'
        )
        wedge = ProjectedEpisode(
            id=str(uuid5(NAMESPACE_URL, f'recorded-episode:{self.uid}:{cid}:{start.isoformat()}')),
            started_at=start,
            last_activity_at=window_end,
            close_reason=close_reason,
            fixed=True,
            conversation_ids=[cid],
            member_activity={cid: window_end},
        )
        self.episodes.append(wedge)
        self.events.append(f'span {cid}: wedge-create {wedge.id}')

    def _merged(self, donor: str, survivor: str) -> None:
        donor, survivor = self._resolve(donor), self._resolve(survivor)
        self.cid_redirect[donor] = survivor
        if donor == survivor:
            return
        owner = self._find(donor)
        if owner is not None:
            fact = owner.recorded_members.pop(donor, None)
            owner.conversation_ids = list(dict.fromkeys(survivor if c == donor else c for c in owner.conversation_ids))
            # Production _repoint_absorbed does not touch member_activity: the
            # donor's dead entry stays in the doc until the next rebuild.
            if fact is not None:
                owner.recorded_members[survivor] = _envelope_merge(
                    owner.recorded_members.get(survivor), fact['start'], fact['end'], fact.get('source')
                )
            # Fold the envelope in the span domain and pin the repointed shape
            # (a later repartition of this component rebuilds it canonically).
            donor_span = self.spans.pop(donor, None)
            if donor_span is not None:
                self.spans[survivor] = _envelope_merge(
                    self.spans.get(survivor), donor_span['start'], donor_span['end'], donor_span.get('source')
                )
            if owner in self.windows:
                self.windows.remove(owner)
                self.episodes.append(owner)
            owner.apply_retained_bounds_if_changed()
            self.events.append(f'merge {donor}->{survivor}: repoint on {owner.id}')
            return
        fact = self.spans.pop(donor, None)
        if fact is not None:
            self.spans[survivor] = _envelope_merge(
                self.spans.get(survivor), fact['start'], fact['end'], fact.get('source')
            )
        self._previous_rows = self._view_rows()
        self._recompute()
        self.events.append(f'merge {donor}->{survivor}: repoint')

    def _discarded(self, cid: str) -> None:
        cid = self._resolve(cid)
        owner = self._find(cid)
        if owner is None:
            self.events.append(f'discard {cid}: dangling (no-op)')
            return
        owner.discarded_conversation_ids = list(dict.fromkeys([*owner.discarded_conversation_ids, cid]))
        owner.apply_retained_bounds_if_changed()
        if not owner.fixed:
            owner.fixed = True
            if owner in self.windows:
                self.windows.remove(owner)
                for c in owner.conversation_ids:
                    self.spans.pop(c, None)
            if owner not in self.episodes:
                self.episodes.append(owner)
            self._previous_rows = self._view_rows()
            self._recompute()
        self.events.append(
            f'discard {cid}: {"freeze" if True else ""} {owner.id} '
            f'bounds=({owner.started_at.strftime("%H:%M:%S")},{owner.last_activity_at.strftime("%H:%M:%S")})'
        )

    # ------------------------------------------------------------------- api
    def apply(self, fact: Any) -> None:
        payload = dict(fact.payload)
        if fact.kind == 'span_recorded':
            self.record_span(fact.cid, _iso(payload['start']), _iso(payload['end']), payload.get('source'))
        elif fact.kind == 'conversation_merged':
            self._merged(fact.cid, payload['survivor'])
        elif fact.kind == 'conversation_discarded':
            self._discarded(fact.cid)
        else:
            raise ValueError(fact.kind)

    def view(self) -> dict:
        windows = sorted(
            [*(e.window() for e in self.windows), *(e.window() for e in self.episodes)],
            key=lambda w: (w['started_at'], w['id']),
        )
        membership: dict[str, str] = {}
        for w in windows:
            for cid in w['conversation_ids']:
                membership[cid] = w['id']
        return {
            'windows': windows,
            'redirects': dict(self.redirects),
            'membership': membership,
            'events': list(self.events),
        }


def replay(uid: str, facts: Iterable[Any], fixed_episodes: Iterable[dict] = ()) -> dict:
    projector = Projector(uid, fixed_episodes)
    for fact in facts:
        projector.apply(fact)
    return projector.view()
