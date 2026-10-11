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


def test_free_text_and_identity_values_cannot_use_an_untyped_property():
    for key, value in [('email', {'type': 'String'}), ('anything', {'type': 'Object'}), ('metadata', {'type': 'Map'}), ('transcript', {'type': 'String'}), ('deviceAddress', {'type': 'String'}), ('duration', {'type': 'double'}), ('payload', {'type': 'num'})]:
        doc = source()
        doc['events'][0]['properties'][key] = {**value, 'wire_name': key}
        assert registry.validate(doc)


def test_int_and_closed_enum_are_admitted_and_render_wire_values():
    doc = source()
    probe = next(item for item in doc['events'] if item['id'] == 'typeExtensionProbe')
    assert probe['properties']['count']['type'] == 'int'
    assert probe['properties']['mode']['values'] == ['off', 'headphones_only', 'always']
    assert registry.validate(doc) == []
    code, _plan = registry.render(doc)
    assert 'final int count;' in code
    assert 'enum TypeExtensionProbeMode' in code
    assert 'headphonesOnly("headphones_only")' in code
    assert '"mode": mode.wireName' in code


def test_enum_rejects_open_or_degenerate_sets():
    doc = source()
    probe = next(item for item in doc['events'] if item['id'] == 'typeExtensionProbe')
    probe['properties']['mode']['values'] = ['off']
    assert registry.validate(doc)
    probe['properties']['mode']['values'] = ['off', 'Off']
    assert registry.validate(doc)
    probe['properties']['mode'] = {'type': 'enum', 'wire_name': 'mode'}
    assert registry.validate(doc)
    doc = source()
    next(item for item in doc['events'] if item['id'] == 'typeExtensionProbe')['properties']['count'] = {
        'type': 'int', 'wire_name': 'count', 'values': [1, 2]
    }
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


def test_legacy_and_unadopted_new_files_remain_free_but_adopted_calls_fail():
    path = 'app/lib/utils/analytics/analytics_manager.dart'
    assert not registry.raw_violations(path, 'analytics.track("new")', 'analytics.track("old")', [])
    assert registry.raw_violations(path, 'analytics.track("new")', 'old', [path])
    assert not registry.raw_violations('app/lib/new.dart', 'analytics.trackEvent("new")', None, [])
    assert not registry.raw_violations('app/lib/new.dart', '// track("comment")', None, [])
    prior = source()
    prior['adopted_files'] = [path]
    assert registry.validate(source(), prior=prior)


def test_single_transport_bridge_and_unrelated_methods_are_distinct():
    bridge = 'AnalyticsManager().track(event.wireName, properties: event.properties);'
    assert not registry.raw_violations(registry.BRIDGE, bridge, None, [])
    assert registry.raw_violations(registry.BRIDGE, bridge + bridge, None, [])
    assert registry.raw_violations(registry.BRIDGE, 'Posthog().capture(eventName: "bad");', None, [])
    assert not registry.raw_violations('app/lib/camera.dart', 'camera.capture(); counter.track();', None, [])
    assert not registry.raw_violations('app/lib/camera.dart', 'print("analytics.track(example)");', None, [])
    assert registry.raw_violations('app/lib/new.dart', 'PlatformManager.instance.analytics.track("new");', None, ['app/lib/new.dart'])


def test_dart_parameter_names_do_not_rename_legacy_wire_properties():
    doc = source()
    event = next(item for item in doc['events'] if item['id'] == 'transcribeLaterToggled')
    event['properties']['enabled']['wire_name'] = 'was_enabled'
    assert registry.validate(doc) == []
    code, plan = registry.render(doc)
    assert '"was_enabled": enabled' in code
    assert 'was_enabled' in plan
    event['properties']['enabled']['wire_name'] = 'email_notifications_enabled'
    assert registry.validate(doc) == [], 'a boolean preference is not an email address'
    event['properties']['enabled']['wire_name'] = 'git_sha'
    assert registry.validate(doc), 'provenance stays SDK-owned'


def test_correlated_journeys_require_paired_vocabulary_and_random_ids():
    doc = source()
    assert registry.validate(doc) == []
    outcome = next(e for e in doc['events'] if e['id'] == 'productJourneyOutcome')
    outcome['correlation'] = {'type': 'user_id', 'field': 'correlation_id'}
    assert registry.validate(doc)
    doc = source()
    outcome = next(e for e in doc['events'] if e['id'] == 'productJourneyOutcome')
    outcome['properties']['journey']['values'].append('unpaired_journey')
    assert registry.validate(doc)
    doc = source()
    doc['events'] = [e for e in doc['events'] if e['phase'] != 'attempt']
    assert registry.validate(doc)


def test_record_reference_cannot_be_repurposed_to_arbitrary_content():
    doc = source()
    event = next(e for e in doc['events'] if e['id'] == 'productValueEvent')
    event['properties']['objectId']['wire_name'] = 'transcript'
    assert registry.validate(doc)
