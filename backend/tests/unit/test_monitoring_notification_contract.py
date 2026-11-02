"""Telegram delivery contracts; execute the real Go template with synthetic alerts."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
MONITORING = ROOT / 'backend/charts/monitoring'
NOTIFICATIONS = MONITORING / 'notifications'


def test_severity_timing_and_actionable_annotations():
    dashboards = {json.loads(path.read_text())['uid'] for path in (MONITORING / 'dashboards').rglob('*.json')}
    for path in [MONITORING / 'alert-rules.json', *sorted((MONITORING / 'alerts').glob('*.json'))]:
        for rule in json.loads(path.read_text()):
            severity = rule['labels']['severity']
            assert severity in {'critical', 'warning', 'ticket'}, rule['uid']
            wait, interval, repeat = ('30s', '5m', '4h') if severity == 'critical' else ('5m', '1h', '24h')
            settings = dict(rule['notification_settings'])
            # Agent-tier rules keep the severity timing but are muted for humans
            # (test_every_alert_rule_declares_tier_owner_and_audience).
            if rule['labels'].get('tier') == 'agent':
                assert settings.pop('mute_time_intervals') == ['omi-tier-silent'], rule['uid']
            assert settings == {
                'receiver': 'Omi - Services Alerting (Telegram)',
                'group_by': ['alertname'],
                'group_wait': wait,
                'group_interval': interval,
                'repeat_interval': repeat,
            }, rule['uid']
            annotations = rule['annotations']
            for key in ('summary', 'user_impact', 'safe_next_action', 'scope'):
                assert annotations[key].strip(), (rule['uid'], key)
            assert annotations.get('__dashboardUid__') in dashboards or annotations.get('dashboard_url', '').startswith(
                'https://monitor.omi.me/d/'
            ), rule['uid']
            # Grafana rejects a rule with __dashboardUid__ but no __panelId__ (HTTP 400 on provisioning PUT);
            # dashboard-only links use the dashboard_url annotation instead.
            assert ('__dashboardUid__' in annotations) == ('__panelId__' in annotations), rule['uid']
            if 'dashboard_url' in annotations:
                assert annotations['dashboard_url'].removeprefix('https://monitor.omi.me/d/') in dashboards, rule['uid']


@pytest.fixture(scope='module')
def render(tmp_path_factory):
    # Go's standard text/template is Grafana's execution engine. No network/modules.
    go = shutil.which('go')
    assert go, 'Go is required to validate Grafana notification templates'
    runner = tmp_path_factory.mktemp('telegram') / 'main.go'
    runner.write_text('''package main
import ("encoding/json"; "os"; "text/template")
func main() {
 var data map[string]interface{}
 if err := json.NewDecoder(os.Stdin).Decode(&data); err != nil { panic(err) }
 t, err := template.ParseFiles(os.Args[1]); if err != nil { panic(err) }
 if err := t.ExecuteTemplate(os.Stdout, "omi.telegram.message", data); err != nil { panic(err) }
}
''')

    def execute(payload):
        return subprocess.run(
            [go, 'run', str(runner), str(NOTIFICATIONS / 'telegram.tmpl')],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout

    return execute


def payload(severity='critical', text='Pusher <5% & "bad" _[pod]_*', count=1, status='firing'):
    alert = {
        'Labels': dict.fromkeys(('alertname', 'pod', 'lane', 'provider'), text) | {'severity': severity},
        'Annotations': dict.fromkeys(('scope', 'summary', 'user_impact', 'safe_next_action', 'runbook'), text),
        'Values': {'B': 12.5, 'C': 1},
        'PanelURL': 'https://monitor.omi.me/d/pusher?viewPanel=3&orgId=1',
        'DashboardURL': 'https://monitor.omi.me/d/pusher',
        'GeneratorURL': 'https://monitor.omi.me/alerting/grafana/test/view',
        'SilenceURL': 'https://monitor.omi.me/alerting/silence/new?alertname=test&severity=critical',
    }
    return {
        'Status': status,
        'Alerts': {
            'Firing': [alert] * count if status == 'firing' else [],
            'Resolved': [alert] * count if status == 'resolved' else [],
        },
    }


def test_plain_text_is_safe_and_actionable(render):
    settings = json.loads((NOTIFICATIONS / 'telegram-settings.json').read_text())
    assert settings['parse_mode'] == 'None'  # HTML/Markdown characters are literal, never entities.
    assert settings['message'] == '{{ template "omi.telegram.message" . }}'
    message = render(payload())
    assert message.startswith('🚨 Pusher <5% & "bad" _[pod]_* |')
    for field in (
        'Summary:',
        'Impact:',
        'Values: map[B:12.5 C:1]',
        'pod=',
        'lane=',
        'provider=',
        'Dashboard/panel:',
        'Next:',
        'Runbook:',
        'Silence:',
        'Rule/all instances:',
    ):
        assert field in message
    assert 'viewPanel=3&orgId=1' in message
    assert render(payload('warning')).startswith('⚠️ DIGEST')
    assert render(payload('ticket')).startswith('⚠️ DIGEST')


def test_real_grafana_silence_url_is_kept(render):
    # Grafana silence URLs carry the rule UID plus every label matcher; measured 256-341 chars for our rules.
    data = payload()
    silence = 'https://monitor.omi.me/alerting/silence/new?alertmanager=grafana&' + '&'.join(
        f'matcher=label{i}%3D%22value-{i:02d}%22' for i in range(10)
    )
    assert 300 < len(silence) < 600
    data['Alerts']['Firing'][0]['SilenceURL'] = silence
    message = render(data)
    assert f'Silence: {silence}' in message
    assert len(message.encode('utf-16-le')) // 2 < 4096


def test_dashboard_url_annotation_is_the_fallback_link(render):
    data = payload()
    alert = data['Alerts']['Firing'][0]
    alert['PanelURL'] = alert['DashboardURL'] = ''
    alert['Annotations']['dashboard_url'] = 'https://monitor.omi.me/d/omi-core-features'
    assert 'Dashboard/panel: https://monitor.omi.me/d/omi-core-features' in render(data)


def test_storm_unicode_links_and_resolved_stay_bounded(render):
    data = payload(count=500)
    data['Alerts']['Firing'][0] = payload(text='🔥' * 10000)['Alerts']['Firing'][0]
    for key in ('PanelURL', 'GeneratorURL', 'SilenceURL'):
        data['Alerts']['Firing'][0][key] = 'https://monitor.omi.me/' + 'a' * 10000
    data['Alerts']['Firing'][0]['Values'] = {'x' * 10000: '🔥' * 10000}
    message = render(data)
    assert len(message.encode('utf-16-le')) // 2 < 4096
    assert 'Firing: 500' in message and 'link unavailable/oversized' in message
    assert '(full text in rule)' in message
    resolved = render(payload(count=500, status='resolved'))
    assert resolved.startswith('✅ RESOLVED') and len(resolved) < 300
    assert 'Recovered: 500' in resolved and 'Next:' not in resolved
    assert 'no instances' in render({'Status': 'resolved', 'Alerts': {'Firing': [], 'Resolved': []}})


def test_split_and_combined_rule_objects_are_byte_identical():
    # Semantic JSON equality alone misses accidental bulk reformatting.
    def objects(path):
        return {json.loads(raw)['uid']: raw for raw in re.findall(r'^  \{\n.*?^  \}', path.read_text(), re.M | re.S)}

    combined = objects(MONITORING / 'alert-rules.json')
    split = {}
    for path in (MONITORING / 'alerts').glob('*.json'):
        split.update(objects(path))
    assert combined.keys() == split.keys()
    for uid, raw in split.items():
        assert combined[uid] == raw, uid


@pytest.mark.parametrize('environment', ['prod', 'dev'])
def test_alert_screenshots_stay_disabled(environment):
    # Screenshot renders call back into the same Grafana; under load they timed out,
    # held its HTTP handlers and made monitor.omi.me flap 502 (2026-10-13).
    values = (MONITORING / f'kube-prometheus-stack/{environment}_omi_monitoring_values.yaml').read_text()
    block = re.search(r'unified_alerting\.screenshots:\n(\s+)capture: (\w+)', values)
    assert block, 'unified_alerting.screenshots must be declared explicitly'
    assert block.group(2) == 'false'
