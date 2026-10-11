"""Negotiation and failed-teardown acceptance from the first broker review."""

import json
import pytest
from .pending import pending
from .test_live_session import rig
from dev_harness import live_session as live


@pytest.mark.parametrize(
    'capabilities',
    [
        {'contract_version': 'unknown', 'capabilities': ['state', 'wait_ready']},
        {'contract_version': 'semantic-controls/v1', 'capabilities': ['capabilities']},
        {'contract_version': 'semantic-controls/v1', 'capabilities': 'state,wait_ready'},
    ],
)
def test_start_cannot_ignore_capability_negotiation(rig, capabilities):
    factory = rig.factory

    def create(spec):
        child = factory(spec)
        send, receive = child.send, child.receive
        ids = set()

        def write(line):
            request = json.loads(line)[0]
            if request.get('params', {}).get('methodName') == 'ext.omi.controls.capabilities':
                ids.add(request['id'])
            send(line)

        def read(timeout_s):
            line = receive(timeout_s)
            if line:
                values = json.loads(line)
                for value in values:
                    if value.get('id') in ids:
                        value['result'] = capabilities
                return json.dumps(values) + '\n'
            return line

        child.send, child.receive = write, read
        return child

    rig.factory = create
    engine = rig.engine()
    try:
        try:
            reply = engine.start()
        except live.LiveError:
            pass  # typed refusal and a blocked receipt are both fail-closed
        else:
            assert reply['outcome'] == 'blocked'
    finally:
        engine.close()


def test_failed_reap_keeps_ownership_and_close_can_retry(rig):
    factory = rig.factory

    def create(spec):
        child = factory(spec)
        send, receive, close = child.send, child.receive, child.close
        replies = []
        attempts = [0]

        def write(line):
            request = json.loads(line)[0]
            if request['method'] == 'app.stop':
                # An application stop acknowledgement does not prove daemon death.
                replies.append(json.dumps([{'id': request['id'], 'result': True}]) + '\n')
            else:
                send(line)

        def read(timeout_s):
            return replies.pop(0) if replies else receive(timeout_s)

        def reap():
            attempts[0] += 1
            if attempts[0] == 1:
                raise OSError('synthetic reap failure: child still alive')
            close()

        child.send, child.receive, child.close = write, read, reap
        return child

    rig.factory = create
    engine = rig.engine()
    assert engine.start()['outcome'] == 'ok'
    with pytest.raises((OSError, live.LiveError)):
        engine.close()
    assert rig.children[0].process.poll() is None
    with pytest.raises(live.LiveError) as error:
        rig.engine().start()
    assert error.value.code == 'worktree-busy'
    engine.close()
    assert rig.children[0].process.poll() is not None
