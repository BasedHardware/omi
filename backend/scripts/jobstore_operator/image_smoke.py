"""Bounded offline actual-image checks; no credentials, state mounts or network."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone
from readiness_contract import READINESS_ENV

PROGRAM = r'''
import hashlib,json,os,pathlib,platform,subprocess,sys
assert os.getuid()==1000 and platform.machine()=='x86_64'
assert sys.version_info[:3]==(3,11,15) and sys.prefix=='/opt/operator-venv'
import psycopg,google.auth
assert psycopg.__version__=='3.2.10'
git=lambda *a:subprocess.check_output(['git','-C','/opt/omi',*a],text=True,timeout=120).strip()
assert git('rev-parse','HEAD')=='97074e78defa1a84b9d39c021e28aa70cf4f2e4e'
assert git('rev-parse','HEAD^{tree}')=='25c38ee2fa9caff96ce6b920fd4f0843e80d6ad0'
assert git('status','--porcelain')==''
assert hashlib.sha256(pathlib.Path('/opt/runner/supervisor.py').read_bytes()).hexdigest()=='1b6a0a1ed5ca8dbc7f8087ae51441539a8aa9b4f4da2171932e2f08af9de699f'
state=pathlib.Path('/home/ubuntu/.local/state/omi-jobstore-reconcile')
assert list(state.iterdir())==[]
subprocess.run([sys.executable,'/build/verify_dependencies.py'],check=True,timeout=60)
# Wrong fixed hostname refuses before ADC acquisition or any SQL attempt.
result=subprocess.run([sys.executable,'/opt/runner/readiness.py'],stdout=subprocess.PIPE,text=True,timeout=60)
report=json.loads(result.stdout)
assert result.returncode==2 and report['result']=='HOLD' and report['failure_class']=='ValueError' and report['failure_stage']=='workload_binding',report
assert set(report)=={'result','failure_class','failure_stage','failure_stage_elapsed_ms','write_attempted','state_initialized','customer_rows_read'}
assert type(report['failure_stage_elapsed_ms']) is int and report['failure_stage_elapsed_ms']>=0
assert all(report[k] is False for k in ('write_attempted','state_initialized','customer_rows_read'))
assert list(state.iterdir())==[]
print(json.dumps({'result':'ACTUAL_IMAGE_OFFLINE_SMOKE_PASS','uid':os.getuid(),'python':sys.version.split()[0],'psycopg':psycopg.__version__,'machine':platform.machine(),'source':git('rev-parse','HEAD'),'state_empty':True,'wrong_workload_refused_before_adc_sql':True,'native_amd64_qualified':False}))
'''


# This runs the image's actual readiness source and full Git checks. The only
# injected seam is a credential refusal, so no ADC/network/SQL call is needed.
SOURCE_REFUSAL_PROGRAM = r'''
import hashlib,json,os,pathlib,sys,time
def require(condition, category):
    if not condition:
        raise ValueError(category)
require(sys.flags.optimize==0, 'SOURCE_REFUSAL_OPTIMIZATION_REFUSED')
sys.path.insert(0,'/opt/runner')
import process_guard
expected='__READINESS_SHA256__'
require(os.getuid()==1000, 'SOURCE_REFUSAL_UID')
require(hashlib.sha256(pathlib.Path('/opt/runner/readiness.py').read_bytes()).hexdigest()==expected, 'SOURCE_REFUSAL_RUNNER_HASH')
child="""
import sys
sys.path.insert(0,'/opt/runner')
import google.auth
from google.auth.exceptions import DefaultCredentialsError
import readiness
calls=[]
def refuse(*args,**kwargs):
    calls.append(True)
    raise DefaultCredentialsError('OFFLINE_CREDENTIAL_REFUSAL')
google.auth.default=refuse
code=readiness.main()
if calls!=[True] or code!=2:
    raise ValueError('SOURCE_REFUSAL_CREDENTIAL_CALL')
raise SystemExit(code)
"""
started=time.monotonic()
guard,raw=process_guard.run_group([sys.executable,'-c',child],timeout=60)
require(guard=={'result':'COMPLETED','exit_code':2}, 'SOURCE_REFUSAL_GUARD')
report=json.loads(raw)
require(set(report)=={'result','failure_class','failure_stage','failure_stage_elapsed_ms','write_attempted','state_initialized','customer_rows_read'}, 'SOURCE_REFUSAL_REPORT')
require(report['result']=='HOLD' and report['failure_class']=='DefaultCredentialsError' and report['failure_stage']=='credentials', 'SOURCE_REFUSAL_STAGE')
require(type(report['failure_stage_elapsed_ms']) is int and report['failure_stage_elapsed_ms']>=0, 'SOURCE_REFUSAL_ELAPSED')
require(all(report[k] is False for k in ('write_attempted','state_initialized','customer_rows_read')), 'SOURCE_REFUSAL_FLAGS')
print(json.dumps({'result':'SOURCE_CHECKS_REACHED_CREDENTIAL_REFUSAL','readiness_sha256':expected,'uid':1000,'full_source_check':True,'credential_refusal_injected':True,'real_credentials_used':False,'sql_called':False,'elapsed_ms':round((time.monotonic()-started)*1000)}))
'''


def source_refusal_program(expected_sha):
    if not isinstance(expected_sha, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha):
        raise ValueError('LOWERCASE_HEX_READINESS_SHA256_REQUIRED')
    return SOURCE_REFUSAL_PROGRAM.replace('__READINESS_SHA256__', expected_sha)


def validate_source_refusal(report, expected_sha):
    source_refusal_program(expected_sha)
    expected = {
        'result': 'SOURCE_CHECKS_REACHED_CREDENTIAL_REFUSAL',
        'readiness_sha256': expected_sha,
        'uid': 1000,
        'full_source_check': True,
        'credential_refusal_injected': True,
        'real_credentials_used': False,
        'sql_called': False,
    }
    if (
        not isinstance(report, dict)
        or set(report) != set(expected) | {'elapsed_ms'}
        or any(type(report.get(key)) is not type(value) or report[key] != value for key, value in expected.items())
        or type(report.get('elapsed_ms')) is not int
        or not 0 <= report['elapsed_ms'] < 60000
    ):
        raise ValueError('REAL_RESOURCE_BOUND_SOURCE_REFUSAL_REQUIRED')
    return report


def run_container(arguments, *, hold=False, readiness=False):
    cid = subprocess.check_output(
        [
            'docker',
            'create',
            '--platform=linux/amd64',
            '--network=none',
            '--read-only',
            '--tmpfs=/tmp:rw,mode=1777',
            '--cap-drop=ALL',
            '--security-opt=no-new-privileges',
            '--cpus=0.5' if readiness else '--cpus=2',
            *(
                ['--hostname=jobstore-reconcile-0', *[f'--env={k}={v}' for k, v in READINESS_ENV.items()]]
                if readiness
                else []
            ),
            '--memory=512m',
            '--memory-swap=512m',
            '--pids-limit=128',
            *arguments,
        ],
        text=True,
        timeout=30,
    ).strip()
    try:
        if not hold:
            result = subprocess.run(
                ['docker', 'start', '-a', cid],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE if readiness else subprocess.STDOUT,
                text=True,
                timeout=240,
            )
            if result.returncode:
                diagnostic = result.stdout
                if readiness and result.stderr:
                    diagnostic += '\n' + result.stderr
                raise RuntimeError(diagnostic[-16384:])
            return result.stdout
        subprocess.run(['docker', 'start', cid], check=True, stdout=subprocess.DEVNULL, timeout=30)
        # Observe logs until the first closed-state line arrives;
        # a separate bounded docker stop owns termination of this exact CID.
        deadline = time.monotonic() + 30
        while True:
            output = subprocess.check_output(['docker', 'logs', cid], text=True, timeout=5)
            if 'CLOSED_NO_RUNTIME_POLICY' in output:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('HOLD_START_DEADLINE')
            time.sleep(0.2)
        subprocess.run(['docker', 'stop', '--time=5', cid], check=True, stdout=subprocess.DEVNULL, timeout=15)
        state = json.loads(subprocess.check_output(['docker', 'inspect', cid], text=True, timeout=10))[0]['State']
        assert state['ExitCode'] == 0 and not state['Running']
        return output + 'HOLD_SIGTERM_EXIT_0\n'
    finally:
        subprocess.run(['docker', 'rm', '-f', cid], stdout=subprocess.DEVNULL, check=True, timeout=30)
