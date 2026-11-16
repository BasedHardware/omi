"""Bounded offline actual-image checks; no credentials, state mounts or network."""

import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

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
assert result.returncode==2 and report=={'result':'HOLD','failure_class':'ValueError','write_attempted':False,'state_initialized':False,'customer_rows_read':False},report
assert list(state.iterdir())==[]
print(json.dumps({'result':'ACTUAL_IMAGE_OFFLINE_SMOKE_PASS','uid':os.getuid(),'python':sys.version.split()[0],'psycopg':psycopg.__version__,'machine':platform.machine(),'source':git('rev-parse','HEAD'),'state_empty':True,'wrong_workload_refused_before_adc_sql':True,'native_amd64_qualified':False}))
'''


def run_container(arguments, *, hold=False):
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
            '--cpus=2',
            '--memory=512m',
            '--pids-limit=128',
            *arguments,
        ],
        text=True,
        timeout=30,
    ).strip()
    try:
        if not hold:
            result = subprocess.run(
                ['docker', 'start', '-a', cid], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=240
            )
            if result.returncode:
                raise RuntimeError(result.stdout)
            return result.stdout
        subprocess.run(['docker', 'start', cid], check=True, stdout=subprocess.DEVNULL, timeout=30)
        # Observe logs until the first closed-state line arrives;
        # a separate bounded docker stop owns termination of this exact CID.
        import time

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
