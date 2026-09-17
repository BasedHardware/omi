"""Active C7 enforcement probes; no PostHog/network access."""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('event_registry', ROOT / 'scripts/check_event_registry.py')
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


def source():
    return json.loads((ROOT / registry.SOURCE).read_text())


def test_real_consumers_and_generated_outputs():
    doc = source()
    assert registry.validate(doc) == []
    for path, text in zip((registry.DART, registry.PLAN), registry.render(doc)):
        assert (ROOT / path).read_text() == text


def test_no_write_only_or_decorative_consumer():
    for consumers in ([], ['not-a-consumer'], ['../../escape']):
        doc = source()
        doc['events'][0]['consumers'] = consumers
        assert registry.validate(doc)


def test_free_text_and_identity_properties_are_rejected():
    for key, value in [('email', {'type': 'bool'}), ('anything', {'type': 'String'}), ('metadata', {'type': 'Map'}), ('transcript', {'type': 'bool'}), ('deviceAddress', {'type': 'bool'})]:
        doc = source()
        doc['events'][0]['properties'][key] = value
        assert registry.validate(doc)


def test_wire_change_or_removal_cannot_silently_break_old_consumers():
    prior = source()
    for field, value in [('wire_name', 'Renamed'), ('properties', {'newField': {'type': 'bool'}})]:
        doc = copy.deepcopy(prior)
        doc['events'][0][field] = value
        assert registry.validate(doc, prior=prior)
    doc = copy.deepcopy(prior)
    doc['events'].pop()
    assert registry.validate(doc, prior=prior)


def test_legacy_growth_allowed_but_adopted_and_new_calls_rejected():
    path = 'app/lib/utils/analytics/analytics_manager.dart'
    assert not registry.raw_violations(path, 'track("new")', 'track("old")', [])
    assert registry.raw_violations(path, 'receiver.track("new")', 'old', [path])
    assert registry.raw_violations('app/lib/new.dart', 'analytics.trackEvent("new")', None, [])
    assert not registry.raw_violations('app/lib/new.dart', '// track("comment")', None, [])
    prior = source()
    prior['adopted_files'] = [path]
    assert registry.validate(source(), prior=prior)
