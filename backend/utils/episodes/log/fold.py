"""Pure incremental episode fold. The log supplies phase and boundary decisions.

Placement uses the ported five-rule projector. Committed decision facts preserve
content, identifiers, and paid-once evidence which pre-migration spans cannot
reconstruct. Checkpoints are an optimization: replaying facts rebuilds them.
"""

from copy import deepcopy
from types import SimpleNamespace

from utils.conversations.phase import derive_episode_phase
from utils.episodes.log.projector import Projector, ProjectedEpisode

GEOMETRY = frozenset(
    {
        'started_at',
        'last_activity_at',
        'recorded_end',
        'closed_at',
        'status',
        'close_reason',
        'conversation_ids',
        'recorded_members',
        'member_activity',
        'discarded_conversation_ids',
        'sources',
    }
)


def automatic(row):
    return (
        row.get('recorded_members') is not None
        and not row.get('discarded_conversation_ids')
        and row.get('status') == 'closed'
        and row.get('close_reason') in {'gap', 'idle', 'hard_cap'}
    )


def episode(row):
    return ProjectedEpisode(
        id=row['id'],
        started_at=row['started_at'],
        last_activity_at=row['last_activity_at'],
        close_reason=row.get('close_reason'),
        status=row.get('status', 'closed'),
        recorded_members=row.get('recorded_members'),
        conversation_ids=row.get('conversation_ids'),
        discarded=row.get('discarded_conversation_ids') or (),
        recorded_end=row.get('recorded_end'),
        member_activity=row.get('member_activity'),
        fixed=not automatic(row),
    )


class Fold:
    def __init__(self, uid, checkpoint=None):
        self.projector = Projector(uid)
        self.metadata = {}
        self.links = {}
        self.receipts = {}
        self.members = {}
        if checkpoint:
            self.metadata = deepcopy(checkpoint['metadata'])
            self.links = deepcopy(checkpoint['links'])
            self.receipts = deepcopy(checkpoint['receipts'])
            self.members = deepcopy(checkpoint.get('members', {}))
            p = self.projector
            for name in ('spans', 'redirects', 'cid_redirect', '_previous_rows'):
                setattr(p, name, deepcopy(checkpoint['projector'][name]))
            p.issued_ids = set(checkpoint['projector']['_issued'])
            for name in ('episodes', 'windows'):
                restored = []
                for item in checkpoint['projector'][name]:
                    ep = ProjectedEpisode(**deepcopy(item['args']))
                    ep.applied_members = frozenset(item['applied_members'])
                    ep.applied_discards = tuple(item['applied_discards'])
                    restored.append(ep)
                setattr(p, name, restored)

    def _seed(self, row, *, replace=False, pin=False):
        p = self.projector
        eid = row['id']
        if eid in self.metadata and not replace:
            return
        self.metadata[eid] = deepcopy(row)
        p.issued_ids.add(eid)
        if row.get('recorded_merged_into'):
            p.redirects[eid] = row['recorded_merged_into']
            return
        for name in ('episodes', 'windows'):
            old = getattr(p, name)
            for previous in old:
                if previous.id == eid:
                    for cid in previous.recorded_members:
                        if cid not in (row.get('recorded_members') or {}):
                            p.spans.pop(cid, None)
            setattr(p, name, [ep for ep in old if ep.id != eid])
        ep = episode(row)
        if ep.fixed or pin:
            p.episodes.append(ep)
            if ep.fixed:
                for cid in ep.conversation_ids:
                    p.spans.pop(cid, None)
            else:
                p.spans.update(deepcopy(ep.recorded_members))
        else:
            p.windows.append(ep)
            p.spans.update(deepcopy(ep.recorded_members))

    def apply(self, event):
        kind, payload = event['kind'], event['payload']
        if kind in {'baseline', 'fence'}:
            self._seed(payload['row'], replace=payload.get('replace', False))
        elif kind == 'member':
            self.members[event['cid']] = deepcopy(payload)
        elif kind in {'member_refresh', 'home_refresh', 'backfill_complete'}:
            pass  # The worker refreshes authoritative member policy before publishing.
        elif kind == 'receipts':
            cid = event['cid']
            self.receipts[cid] = sorted(set(self.receipts.get(cid, [])) | set(payload['ids']))
        elif kind == 'baseline_link':
            self.links.setdefault(event['cid'], deepcopy(payload))
        elif kind == 'link':
            self.links[event['cid']] = deepcopy(payload)
        elif kind == 'mutation':
            for row in payload.get('before', []):
                self._seed(row)
            span = payload.get('span')
            if span:
                self.projector.record_span(span['cid'], span['start'], span['end'], span.get('source'))
            for row in payload['after']:
                old = self.metadata.get(row['id'], {})
                # Lifecycle facts go through the shared phase derivation; there is no
                # separately mutable phase/status authority in the fold.
                previous_phase, next_phase = derive_episode_phase(old), derive_episode_phase(row)
                if row.get('recorded_merged_into'):
                    self.projector.redirects[row['id']] = row['recorded_merged_into']
                elif not span and (
                    previous_phase != next_phase
                    or not automatic(row)
                    or any(old.get(k) != row.get(k) for k in GEOMETRY)
                ):
                    self._seed(
                        row,
                        replace=True,
                        pin=automatic(row)
                        and set(old.get('conversation_ids') or []) != set(row.get('conversation_ids') or []),
                    )
                self.metadata[row['id']] = deepcopy(row)
            for cid, link in payload.get('links', {}).items():
                self.links[cid] = deepcopy(link)
            for cid, ids in payload.get('receipts', {}).items():
                self.receipts[cid] = sorted(set(self.receipts.get(cid, [])) | set(ids))
        elif kind in {'span_recorded', 'conversation_merged', 'conversation_discarded'}:
            self.projector.apply(SimpleNamespace(kind=kind, cid=event['cid'], payload=payload))
        else:
            raise ValueError(f'unknown episode fact: {kind}')
        # Diagnostic traces are not durable state and must not grow per delivery.
        self.projector.events.clear()

    def rows(self):
        p = self.projector
        rows = {}
        for ep in [*p.windows, *p.episodes]:
            window = ep.window()
            window.pop('fixed')
            row = {**deepcopy(self.metadata.get(ep.id, {})), **window, **ep.row()}
            if ep.fixed:
                row['sources'] = sorted(
                    set(row.get('sources') or []) | set(self.metadata.get(ep.id, {}).get('sources') or [])
                )
                row['closed_at'] = self.metadata.get(ep.id, {}).get('closed_at')
                if self.metadata.get(ep.id, {}).get('recorded_members') is None:
                    row.pop('recorded_members', None)  # A wedge must never become automatic on replay.
            rows[ep.id] = row
        for eid, target in p.redirects.items():
            rows[eid] = {**deepcopy(self.metadata.get(eid, {})), 'id': eid, 'recorded_merged_into': target}
        return rows

    def checkpoint(self):
        p = self.projector
        state = {name: deepcopy(getattr(p, name)) for name in ('spans', 'redirects', 'cid_redirect', '_previous_rows')}
        state['_issued'] = sorted(p.issued_ids)
        for name in ('episodes', 'windows'):
            state[name] = [
                {
                    'args': {
                        'id': ep.id,
                        'started_at': ep.started_at,
                        'last_activity_at': ep.last_activity_at,
                        'close_reason': ep.close_reason,
                        'status': ep.status,
                        'recorded_members': ep.recorded_members,
                        'conversation_ids': ep.conversation_ids,
                        'discarded': ep.discarded_conversation_ids,
                        'recorded_end': ep.recorded_end,
                        'fixed': ep.fixed,
                        'member_activity': ep.member_activity,
                    },
                    'applied_members': sorted(ep.applied_members),
                    'applied_discards': list(ep.applied_discards),
                }
                for ep in getattr(p, name)
            ]
        return deepcopy(
            {
                'projector': state,
                'metadata': self.metadata,
                'links': self.links,
                'receipts': self.receipts,
                'members': self.members,
            }
        )
