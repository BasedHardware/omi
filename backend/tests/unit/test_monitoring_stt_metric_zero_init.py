"""Startup exposition contract for alert metrics in the two Python registries.

Scope: every Prometheus expr in alerts/*.json, intersected with metrics defined
in utils/metrics.py and llm_gateway/gateway/metrics.py (regardless of job selector).
Exporter, GPU and other service registries are outside this contract. This checks
family availability, not completeness of every possible label selector.
"""

import ast
import importlib
import json
import re
from pathlib import Path

import pytest
from prometheus_client import Counter, Gauge, Histogram

BACKEND = Path(__file__).resolve().parents[2]

# Existing sparse series are debt, not healthy zeroes. Remove entries as their
# startup paths are added; don't mask new alert metrics with a blanket exception.
DECLARED_SPARSE = {
    'llm_gateway_requests_total': 'Route/outcome children appear only when a real request finishes.',
    'omi_sync_dispatch_attempts_total': 'Dispatch lane/outcome children appear only on sync dispatch.',
    'omi_live_stt_terminal_failures_total': 'Provider/phase failure children appear only on live-STT failure.',
    'omi_live_stt_accepted_total': 'Provider/platform/environment children appear only on accepted STT traffic.',
    'omi_live_stt_terminal_total': 'Provider/outcome/phase children appear only at live-STT termination.',
    'omi_sync_transcription_job_total': (
        'Service/outcome children appear only when a sync job reaches a terminal outcome; the failure-reason '
        'step rule needs >= 50 reason jobs per 60m and treats a missing baseline as new.'
    ),
    'omi_listen_accepted_total': 'Source/platform children appear only when a listen session is accepted.',
    'omi_client_journey_terminal_total': (
        'Client journey children are traffic-created to bound cardinality. Journey SLOs zero-fill only the '
        'bad numerator against an observed valid denominator; absence is owned by scrape/signal health.'
    ),
}


def _module_calls(path):
    """Calls outside function/class bodies: defining an initializer isn't enough."""
    calls = set()

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            pass

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            self.generic_visit(node)

    Visitor().visit(ast.parse(path.read_text(encoding='utf-8')))
    return calls


def _startup_inventory():
    # Only pure instrumentation modules are imported; no servers, pollers or
    # provider clients are started. Import executes their real zero-init paths.
    metrics = importlib.import_module('utils.metrics')
    gateway_metrics = importlib.import_module('llm_gateway.gateway.metrics')
    for name in ('fallback', 'transcription', 'subscription_events'):
        importlib.import_module(f'utils.observability.{name}')
    importlib.import_module('utils.stt.stream_close')
    connect = importlib.import_module('utils.stt.connect_metrics')
    # streaming.py is a heavy provider entrypoint. Prove its startup call is
    # wired, then invoke the same lightweight initializer without importing SDKs.
    assert 'initialize_stt_provider_connect_children' in _module_calls(BACKEND / 'utils/stt/streaming.py')
    connect.initialize_stt_provider_connect_children()
    inventory = {}
    for module in (metrics, gateway_metrics):
        for metric in vars(module).values():
            if not isinstance(metric, (Counter, Gauge, Histogram)):
                continue
            names = {metric._name}
            if isinstance(metric, Counter):
                names = {metric._name + '_total'}
            elif isinstance(metric, Histogram):
                names |= {metric._name + suffix for suffix in ('_bucket', '_count', '_sum')}
            for name in names:
                inventory[name] = metric
    return inventory


def _alert_metric_references():
    references = set()
    expressions = 0
    for path in sorted((BACKEND / 'charts/monitoring/alerts').glob('*.json')):
        for rule in json.loads(path.read_text(encoding='utf-8')):
            for query in rule.get('data', []):
                model = query.get('model') or {}
                if not (
                    query.get('datasourceUid') == 'prometheus'
                    or (model.get('datasource') or {}).get('type') == 'prometheus'
                ):
                    continue
                expr = model.get('expr')
                if not isinstance(expr, str) or not expr:
                    continue
                expressions += 1
                # Preserve an explicit __name__ selector, then mask strings so
                # label values cannot be mistaken for metric identifiers.
                references.update(re.findall(r'__name__\s*=\s*"([a-zA-Z_:][a-zA-Z0-9_:]*)"', expr))
                masked = re.sub(r'"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|`[^`]*`', '', expr)
                references.update(re.findall(r'\b[a-zA-Z_:][a-zA-Z0-9_:]*\b', masked))
    assert expressions > 50, 'Prometheus alert expression discovery stopped working'
    return references


@pytest.fixture(scope='module')
def startup_inventory():
    return _startup_inventory()


def test_alert_metrics_have_startup_children_or_declared_sparse_debt(startup_inventory):
    inventory = startup_inventory
    references = _alert_metric_references() & inventory.keys()
    assert 'omi_stt_stream_close_total' in references
    assert len(references) >= 25, 'registry scope unexpectedly shrank'
    sparse = set()
    for name in references:
        metric = inventory[name]
        # Gauges and unlabelled metrics satisfy the requested family contract.
        if isinstance(metric, Gauge) or not metric._labelnames:
            continue
        if not any(sample.name == name for family in metric.collect() for sample in family.samples):
            sparse.add(name)
    assert sparse == DECLARED_SPARSE.keys(), (
        f'Undeclared sparse alert metrics: {sorted(sparse - DECLARED_SPARSE.keys())}; '
        f'remove obsolete sparse declarations: {sorted(DECLARED_SPARSE.keys() - sparse)}'
    )
    assert all(reason.strip() for reason in DECLARED_SPARSE.values())


def test_close_initializer_is_wired_for_streaming_and_direct_vendor_users():
    initializer = 'initialize_stt_stream_close_children'
    assert initializer in _module_calls(BACKEND / 'utils/stt/streaming.py')
    assert initializer in _module_calls(BACKEND / 'utils/stt/stream_close.py')
