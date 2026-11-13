"""FS admission adapter: customer ledger plus intent, without live FS queue rows.

Used only by explicit Handoff injection into the existing admission function.
Native/partial/provider/coalesced reservation adapters are not implemented here;
they refuse before any write instead of falling back to FS queue ownership.
"""

from copy import deepcopy

from database.jobstore.authority import AuthorityRefused, fingerprint


class IntentTransaction:
    def __init__(self, view, segment_ids):
        self.view = view
        self.segment_ids = set(segment_ids)
        self.plans = {}

    def get(self, table, key):
        if table in {'jobs', 'intakes'}:
            if table == 'jobs' and key not in self.segment_ids:
                raise AuthorityRefused('cross-record admission requires its PG reservation adapter')
            return deepcopy(self.plans.get((table, key), {}))
        if table not in {'content', 'conversations', 'artifacts'}:
            raise AuthorityRefused('admission queue read requires its PG adapter')
        return self.view.get(table, key)

    def put(self, table, key, value):
        if table in {'jobs', 'intakes'}:
            if table == 'intakes':
                # Original-capture repair lineage keeps its existing FS receipt
                # and lifetime. It never enters PG queue custody.
                self.view.put(table, key, value)
                value = {name: item for name, item in value.items() if name != 'repair_lineage'}
            self.plans[(table, key)] = deepcopy(value)
        elif table in {'content', 'artifacts'}:
            self.view.put(table, key, value)
        else:
            raise AuthorityRefused('unexpected admission writer')

    def patch(self, table, key, fields):
        raise AuthorityRefused('native recording requires its PG reservation adapter')

    def defer_set(self, ref, value):
        raise AuthorityRefused('provider cohort requires its typed PG intent adapter')


def plan_enqueue(tx, item, now, *, policy):
    previous = tx.get('jobs', item.segment_id)
    if previous:
        raise AuthorityRefused('duplicate segment in immutable admission plan')
    tx.put('jobs', item.segment_id, {**item.to_dict(), 'policy': policy.to_dict(), 'enqueued_at': now})
    return True


class IntentStore:
    def __init__(self, source, handoff, binding):
        if source.namespace != handoff.ticket.namespace or getattr(source, 'queue_authority', None) is not None:
            raise AuthorityRefused('intent source requires a matching customer store, not an FS queue writer')
        self.source, self.handoff, self.binding = source, handoff, binding

    def run(self, body):
        def commit(view):
            targets = [self.binding.target_conversation_id] if self.binding.target_conversation_id else []
            view.check_privacy(self.binding.owner_id, targets, self.binding.privacy_generation)
            plan = IntentTransaction(view, self.binding.segment_ids)
            result = body(plan)
            if plan.plans:
                jobs = {key: value for (table, key), value in plan.plans.items() if table == 'jobs'}
                if set(jobs) != set(self.binding.segment_ids):
                    raise AuthorityRefused('incomplete admission sibling plan')
                targets = sorted({job['conversation_id'] for job in jobs.values() if job.get('conversation_id')})
                if self.binding.target_conversation_id:
                    targets = sorted(set(targets) | {self.binding.target_conversation_id})
                for target in targets:
                    view.check_privacy(self.binding.owner_id, (target,), self.binding.privacy_generation)
                payload = {
                    'jobs': jobs,
                    'intakes': {key: value for (table, key), value in plan.plans.items() if table == 'intakes'},
                }
                # body writes above remain buffered in the original view. These
                # authority/intent reads happen before the first raw FS write.
                self.handoff.stage(view.transaction, self.binding.job_id, self.binding.owner_id, targets, payload)
            elif result.get('outcome') == 'batch':
                # A legacy FS ledger alone cannot attest PG custody after a
                # cutover. Never acknowledge accepted work with no durable intent.
                self.handoff.authority.check(view.transaction, phases=('PG_OPEN',))
                source = self.handoff.ref('intent', result['job_id']).get(transaction=view.transaction).to_dict() or {}
                intent = source.get('intent', {})
                if (
                    intent.get('uid') != self.binding.owner_id
                    or intent.get('identity') != result['job_id']
                    or intent.get('namespace') != self.handoff.ticket.namespace
                    or intent.get('epoch') != self.handoff.ticket.value
                    or source.get('fingerprint') != fingerprint(intent)
                ):
                    raise AuthorityRefused('existing batch ledger has no matching PG admission intent')
            return result

        return self.source.run(commit)
