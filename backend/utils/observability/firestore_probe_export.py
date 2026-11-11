"""Export existing in-process counters; never construct a client or issue a read."""

from contextlib import contextmanager
import json
import logging
import math
import os
import tempfile

from database.firestore_document_probe import FIRESTORE_BILLED_READS, FIRESTORE_BILLED_READS_BY_CALLER, bound_caller

logger = logging.getLogger(__name__)
COLLECTORS = (FIRESTORE_BILLED_READS, FIRESTORE_BILLED_READS_BY_CALLER)
# Sample names and label keys of the served counters, pinned from their
# declarations in database/firestore_document_probe.py. prometheus_client
# exposes them only via private attributes (_name/_labelnames), which backend
# typecheck forbids; the drift pin in test_record_seal_cluster_repair.py
# fails if the probe renames either side.
COUNTER_SAMPLES = {
    'omi_firestore_billed_reads_total': (
        FIRESTORE_BILLED_READS,
        ('collection', 'kind', 'tier'),
    ),
    'omi_firestore_billed_reads_by_caller_total': (
        FIRESTORE_BILLED_READS_BY_CALLER,
        ('collection', 'kind', 'caller'),
    ),
}
CHILD_FD_ENV = 'OMI_FIRESTORE_PROBE_TERMINAL_FD'
MAX_TERMINAL_BYTES = 4 * 1024 * 1024


def _emit(payload, level=logging.INFO):
    # Repair suppresses dependency diagnostics with logging.disable(). Like its
    # existing aggregate emitter, explicitly handle only our counts-only record.
    record = logger.makeRecord(logger.name, level, '', 0, json.dumps(payload, allow_nan=False), (), None)
    logger.handle(record)


def _unavailable():
    _emit({'event': 'firestore_probe_terminal', 'outcome': 'unavailable'}, logging.WARNING)


def register_probe_collectors(registry):
    for collector in COLLECTORS:
        registry.register(collector)


def terminal_totals():
    # Only totals and the producer's bounded labels; no created timestamps,
    # document IDs, query operands, or a second SDK patch.
    return [
        [sample.name, sample.labels, sample.value]
        for collector in COLLECTORS
        for family in collector.collect()
        for sample in family.samples
        if sample.name.endswith('_total')
    ]


@contextmanager
def terminal_probe_totals(service=None, *, fd=None, log_empty=True):
    """Finally runs on success/error/SIGTERM unwind; SIGKILL cannot be counted."""
    try:
        yield
    finally:
        try:
            if fd is not None:
                # A regular anonymous file cannot block on a full stdout pipe.
                # The parent reads it only after wait(), exactly once.
                with os.fdopen(os.dup(int(fd)), 'w') as output:
                    json.dump(terminal_totals(), output, separators=(',', ':'), allow_nan=False)
            elif service is not None:
                rows = terminal_totals()
                if rows or log_empty:
                    _emit({'event': 'firestore_probe_terminal', 'service': service, 'series': len(rows)})
                for metric, labels, value in rows:
                    _emit(
                        {
                            'event': 'firestore_probe_terminal_sample',
                            'service': service,
                            'metric': metric,
                            'labels': labels,
                            'value': value,
                        }
                    )
        except Exception:
            # Observability must preserve the job's original result/exception.
            # A child must never add diagnostics to its private row-result pipe;
            # the parent reports a missing/invalid snapshot after reap instead.
            if fd is None:
                _unavailable()


def launch_with_probe(factory, *args, **kwargs):
    """Give a disposable child an aggregate-only fd, separate from row IPC."""
    output = None
    try:
        output = tempfile.TemporaryFile(mode='w+b')
    except OSError:
        _unavailable()
    if output is not None:
        kwargs['env'] = {**kwargs.get('env', os.environ), CHILD_FD_ENV: str(output.fileno())}
        kwargs['pass_fds'] = (*kwargs.get('pass_fds', ()), output.fileno())
    try:
        process = factory(*args, **kwargs)
    except BaseException:
        if output is not None:
            output.close()
        raise
    process._firestore_probe_output = output
    return process


def collect_child_probe(process):
    """Fold terminal child reads into the parent's served counters at reap."""
    output = getattr(process, '_firestore_probe_output', None)
    if output is None:
        return
    process._firestore_probe_output = None  # Repeated cleanup must not double count.
    try:
        with output:
            output.seek(0)
            raw = output.read(MAX_TERMINAL_BYTES + 1)
        if not raw or len(raw) > MAX_TERMINAL_BYTES:
            raise ValueError('missing or oversized terminal aggregate')
        counters = COUNTER_SAMPLES
        rows = json.loads(raw)
        # Validate the whole snapshot before incrementing any parent counter.
        for name, labels, value in rows:
            expected = counters.get(name)
            if expected is None or set(labels) != set(expected[1]):
                raise ValueError('invalid terminal metric')
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('invalid terminal total')
        for name, labels, value in rows:
            if 'caller' in labels:
                labels = {**labels, 'caller': bound_caller(labels['caller'])}
            counters[name][0].labels(**labels).inc(value)
    except Exception:
        _unavailable()
