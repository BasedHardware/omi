"""Worker IO telemetry with closed labels and no content or identifiers."""

from prometheus_client import Counter, Histogram

ADMISSION = Counter('omi_batch_pipeline_admission_receipts_total', 'Client admission receipts', ['outcome'])
STRICT_VAD = Counter('omi_batch_pipeline_strict_vad_shadow_total', 'CPU-only strict VAD comparison', ['outcome'])
STRICT_CPU = Histogram('omi_batch_pipeline_strict_vad_shadow_cpu_seconds', 'Thread CPU consumed by strict VAD shadow')
COLLECTORS = (ADMISSION, STRICT_VAD, STRICT_CPU)


def admission(outcome):
    if outcome not in {'received', 'timeout', 'transport', 'invalid_receipt', 'unconfigured'}:
        raise ValueError('invalid admission outcome')
    try:
        ADMISSION.labels(outcome).inc()
    except Exception:
        pass


def strict_vad(silent, nonempty):
    outcomes = ['unavailable'] if silent is None else ['evaluated']
    if silent:
        outcomes.append('strict_silent')
        if nonempty:
            outcomes.append('strict_silent_pyannote_nonempty')
    try:
        for outcome in outcomes:
            STRICT_VAD.labels(outcome).inc()
    except Exception:
        pass
