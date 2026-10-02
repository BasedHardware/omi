"""T10: operations must still own the lease at publication, not only admission."""

import json
from dataclasses import replace
import pytest
from .pending import pending
from .test_live_session import rig
from dev_harness import live_session as live


@pytest.mark.parametrize("operation", ["start", "reload", "restart"])
def test_lease_roll_during_readiness_cannot_advance_loaded_identity(rig, operation):
    factory = rig.factory
    armed = [operation == 'start']

    def create(spec):
        child = factory(spec)
        send = child.send

        def write(line):
            if armed[0] and 'ext.omi.controls.state' in line:
                armed[0] = False
                rig.lease['generation'] += 1
            send(line)

        child.send = write
        return child

    rig.factory = create
    engine = rig.engine()
    try:
        if operation == 'start':
            reply = engine.start()
        else:
            prior = engine.start()['evidence']['live']
            rig.stamp = replace(rig.stamp, inputs_sha256='f' * 64)
            armed[0] = True
            reply = engine.request(operation, generation=1)
        assert reply['outcome'] == 'blocked', reply
        assert reply['error_code'] == 'stale-session'
        assert reply['evidence']['live']['generation'] == 1
        assert reply['evidence']['live']['loaded_source'] == (None if operation == 'start' else prior['loaded_source'])
        assert reply['evidence']['live']['loaded_sequence'] == (0 if operation == 'start' else prior['loaded_sequence'])
    finally:
        engine.close()


def test_readiness_requires_boolean_true_not_truthy_values(rig):
    factory = rig.factory

    def create(spec):
        child = factory(spec)
        receive = child.receive

        def read(timeout_s):
            line = receive(timeout_s)
            if line:
                values = json.loads(line)
                for value in values:
                    result = value.get('result')
                    if isinstance(result, dict) and 'readiness' in result:
                        result['readiness'] = {k: 'false' for k in result['readiness']}
                return json.dumps(values) + '\n'
            return line

        child.receive = read
        return child

    rig.factory = create
    engine = rig.engine()
    try:
        try:
            reply = engine.start()
        except live.LiveError:
            return
        assert reply['outcome'] == 'blocked', reply
    finally:
        engine.close()


def test_negotiation_error_cannot_restore_cached_ready_state(rig):
    factory = rig.factory
    armed = [False]

    def create(spec):
        child = factory(spec)
        receive = child.receive

        def read(timeout_s):
            line = receive(timeout_s)
            if line:
                values = json.loads(line)
                for value in values:
                    result = value.get('result')
                    if armed[0] and isinstance(result, dict) and 'capabilities' in result:
                        value.pop('result')
                        value['error'] = {'code': -32000, 'message': 'synthetic'}
                return json.dumps(values) + '\n'
            return line

        child.receive = read
        return child

    rig.factory = create
    engine = rig.engine()
    try:
        prior = engine.start()['evidence']['live']
        armed[0] = True
        try:
            reply = engine.request('reload', generation=1)
        except live.LiveError:
            pass
        status = engine.request('status', generation=1)
        assert status['result']['state'] != 'ready', status
        assert status['evidence']['live']['loaded_source'] == prior['loaded_source']
        assert status['evidence']['live']['loaded_sequence'] == prior['loaded_sequence']
        reloads = [
            json.loads(path.read_text())['live']
            for path in rig.directory.glob('operations/*/evidence.json')
            if json.loads(path.read_text())['live']['operation'] == 'reload'
        ]
        assert len(reloads) == 1 and reloads[0]['outcome'] == 'blocked'
    finally:
        armed[0] = False
        engine.close()


def test_authorization_header_is_redacted_before_retained_logs(rig):
    secret = "SYNTHETIC-unrelated-credential-42"
    factory = rig.factory
    armed = [False]

    def create(spec):
        child = factory(spec)
        receive = child.receive

        def read(timeout_s):
            if armed[0]:
                armed[0] = False
                return json.dumps(
                    [{"event": "app.log", "params": {"log": "Authorization: Bearer " + secret, "error": False}}]
                )
            return receive(timeout_s)

        child.receive = read
        return child

    rig.factory = create
    engine = rig.engine()
    try:
        assert engine.start()["outcome"] == "ok"
        armed[0] = True
        assert engine.request("reload", generation=1)["outcome"] == "ok"
        reply = engine.request("logs", generation=1)
        assert secret not in json.dumps(reply)
        for path in rig.directory.glob("operations/*/evidence.json"):
            assert secret not in path.read_text()
    finally:
        engine.close()
