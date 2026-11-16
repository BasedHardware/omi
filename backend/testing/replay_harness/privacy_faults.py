"""Closed applicability labels and evidence checks for synthetic cache faults."""

FSR_FAMILIES = frozenset({'deletion_marker', 'tombstone', 'legal_hold', 'subscription'})
REDIS_FAULTS = frozenset({'redis_down', 'drop_invalidation', 'begin_loss'})


def not_applicable_reason(family, fault):
    if fault in REDIS_FAULTS and family not in FSR_FAMILIES:
        return 'reader_and_writer_do_not_use_fsr_redis'
    if fault == 'request_memo' and family not in {'deletion_marker', 'subscription'}:
        return 'reader_does_not_use_request_read_dedupe'
    return None


def fault_applied(fault, evidence, *, family=None):
    injected = evidence.get('injected', {})
    if fault == 'redis_down':
        return sum(injected.values()) > 0
    if fault == 'drop_invalidation':
        return injected.get('begin', 0) > 0 and injected.get('end', 0) > 0
    if fault == 'begin_loss':
        return injected.get('begin', 0) > 0 and evidence.get('successful', {}).get('end', 0) > 0
    if fault in {'concurrent', 'reader_during_writer'}:
        return (
            evidence.get('synchronized_writers') == (2 if fault == 'concurrent' else 1)
            and evidence.get('overlap_reads') == 1
        )
    if fault == 'request_memo':
        if family == 'deletion_marker':
            reads = evidence.get('request_redis_probe_reads', [])
            return (
                all(
                    evidence.get(key)
                    for key in (
                        'request_memo_absent',
                        'independent_writer_scope',
                        'reader_scope_preserved',
                        'request_deletion_observed',
                    )
                )
                and evidence.get('request_redis_warm_reads') == 2
                and bool(reads)
                and all(count == 1 for count in reads)
            )
        return all(evidence.get(key) for key in ('request_memo_warmed', 'request_memo_hit', 'request_memo_cleared'))
    return False  # Baselines are useful controls, never verified fault samples.
