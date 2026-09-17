"""Subprocess fixture for Flutter 3.44.5 daemon.dart's machine wire.

No device/SDK/network. Modes inject faults after a real stdin command, not
precomputed broker results. Transcript proves the engine sent the right RPC.
"""
import json
import os
from pathlib import Path
import sys

mode, transcript, app_id, device_id = sys.argv[1:]


def emit(value):
    print(json.dumps([value]), flush=True)


emit({'event': 'daemon.connected', 'params': {'version': '0.6.1', 'pid': os.getpid()}})
emit({'event': 'app.start', 'params': {'appId': app_id, 'deviceId': device_id,
     'directory': str(Path.cwd()), 'supportsRestart': True, 'launchMode': 'run', 'mode': 'debug'}})
emit({'event': 'app.debugPort', 'params': {'appId': app_id, 'port': 12345,
     'wsUri': 'ws://127.0.0.1:12345/private-vm-auth/ws'}})
emit({'event': 'app.started', 'params': {'appId': app_id}})
for line in sys.stdin:
    request, = json.loads(line)
    with Path(transcript).open('a') as out:
        out.write(json.dumps(request) + '\n')
    method, params = request['method'], request.get('params', {})
    if params.get('appId') != app_id:
        emit({'id': request['id'], 'error': 'wrong appId'})
        continue
    if method == 'app.restart':
        if mode == 'die':
            sys.exit(7)
        if mode == 'wedge':
            continue
        emit({'event': 'app.log', 'params': {'appId': app_id, 'log': 'fixture progress', 'error': False}})
        emit({'id': 99999, 'result': {'code': 0, 'message': 'unrelated'}})
        if mode == 'reject':
            result = {'code': 1, 'message': 'Reload rejected: class changed'}
        elif mode == 'missing-code':
            result = {'message': 'compiled'}
        else:
            result = {'code': 0, 'message': ''}
        emit({'id': request['id'], 'result': result})
    elif method == 'app.callServiceExtension':
        name = params['methodName']
        if name == 'ext.omi.controls.capabilities':
            result = {'contract_version': 'semantic-controls/v1',
                      'capabilities': ['capabilities', 'state', 'wait_ready', 'navigate', 'fault']}
        elif name in ('ext.omi.controls.state', 'ext.omi.controls.wait_ready'):
            state = {'contract_version': 'semantic-controls/v1',
                     'profile': 'mobileBeta' if mode == 'wrong-runtime' else 'localDev',
                     'readiness': {'signedIn': True, 'routed': mode != 'unready', 'captureIdle': True},
                     'principal': {'uid': 'fixture-user', 'signed_in': True}, 'route': '/home'}
            result = {'ok': True, 'state': state} if name.endswith('wait_ready') else state
        elif name == 'ext.omi.controls.navigate':
            result = {'ok': True}
        elif name == 'ext.omi.controls.fault':
            emit({'id': request['id'], 'error': {'code': -32602, 'message': 'unknown fault'}})
            continue
        else:
            emit({'id': request['id'], 'error': 'unknown extension'})
            continue
        emit({'id': request['id'], 'result': result})
    elif method == 'app.stop':
        emit({'event': 'app.stop', 'params': {'appId': app_id}})
        emit({'id': request['id'], 'result': True})
        sys.exit(0)
    else:
        emit({'id': request['id'], 'error': 'unknown method'})
