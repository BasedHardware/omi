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
            assert rule['notification_settings'] == {
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
