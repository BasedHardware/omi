"""Bounded offline actual-image checks; no credentials, state mounts or network."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone
from readiness_contract import READINESS_ENV
import qualification_profile as P

PROGRAM = r'''
import hashlib,json,os,pathlib,platform,subprocess,sys
assert os.getuid()==1000 and platform.machine()=='x86_64'
assert sys.version_info[:3]==(3,11,15) and sys.prefix=='/opt/operator-venv'
import psycopg,google.auth
assert psycopg.__version__=='3.2.10'
git=lambda *a:subprocess.check_output(['git','--no-optional-locks','-c','core.fsmonitor=false','-c','core.untrackedCache=false','-c','safe.directory=/opt/omi','-C','/opt/omi',*a],text=True,timeout=120).strip()
assert git('rev-parse','HEAD')=='c2824362c2a52925def3ef83f13c3b58487a6aa0'
assert git('rev-parse','HEAD^{tree}')=='a5c8acbd193b6b85661c9fe91759b2ec0eb80608'
assert git('status','--porcelain','--untracked-files=all')==''
assert hashlib.sha256(pathlib.Path('/opt/runner/supervisor.py').read_bytes()).hexdigest()=='1b6a0a1ed5ca8dbc7f8087ae51441539a8aa9b4f4da2171932e2f08af9de699f'
import pwd,shutil
assert pwd.getpwuid(1000).pw_dir==os.getenv('HOME')=='/home/ubuntu'
sys.path.insert(0,'/opt/runner')
import general_copy_catalog as catalog
assert hashlib.sha256(pathlib.Path(catalog.__file__).read_bytes()).hexdigest()=='98a8f98bc4fac0981803497db3fd3ec0a3a82c9fe4db2071d0ee3c0fe129e4ec'
assert hashlib.sha256(pathlib.Path('/opt/runner/general_copy_catalog_contract.py').read_bytes()).hexdigest()=='7f08d86417ec6422717b54c541a8779854572f1830afcee946b3c415b73ae4b2'
assert hashlib.sha256(pathlib.Path('/opt/runner/general_copy_catalog_structure.json').read_bytes()).hexdigest()=='d12b6b5eee4d74842cf99706003ad32633e62c69e4b98a69bd44338d24315de7'
assert hashlib.sha256(pathlib.Path('/opt/runner/process_guard.py').read_bytes()).hexdigest()=='6309e8242ad2469cfc2076379a61a79c5dbb89aa7faf5d26dba9aeade6b67400'
# Actual general command import/parser, before clients, state or any auth.
cli=subprocess.run([sys.executable,'-E','-s','-B','-m','database.jobstore','reconcile-page','--help'],capture_output=True,text=True,timeout=60)
assert cli.returncode==0 and '--max-primary-reads' in cli.stdout and '--state-file' in cli.stdout,(cli.returncode,cli.stderr)
assert subprocess.run([sys.executable,'-I','-B','/opt/runner/general_copy_catalog.py','--help'],stdout=subprocess.DEVNULL,timeout=10).returncode==0
print(json.dumps({'result':'GENERAL_COPIER_CLI_IMPORT_PASS','help_sha256':hashlib.sha256(cli.stdout.encode()).hexdigest(),'git_path':shutil.which('git'),'git_sha256':hashlib.sha256(pathlib.Path(shutil.which('git')).read_bytes()).hexdigest(),'python_resolved':str(pathlib.Path(sys.executable).resolve()),'python_sha256':hashlib.sha256(pathlib.Path(sys.executable).read_bytes()).hexdigest()}))
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


# This runs corrected catalog verify_source over ALL working blobs/ignored files.
# The only auth seam injects a refusal before credentials or SQL; native timing
# uses the existing0.5CPU/512MiB resource flag, without reducing source scope.
SOURCE_REFUSAL_PROGRAM = 'import hashlib,json,os,pathlib,sys,time\nif sys.flags.optimize: raise ValueError(\'SOURCE_REFUSAL_OPTIMIZATION_REFUSED\')\nsys.path.insert(0,\'/opt/runner\')\nimport process_guard\nexpected=\'__CATALOG_SHA256__\'\nif os.getuid()!=1000 or hashlib.sha256(pathlib.Path(\'/opt/runner/general_copy_catalog.py\').read_bytes()).hexdigest()!=expected:raise ValueError(\'FIXED_CATALOG_BYTES_UID_REQUIRED\')\nchild="""\nimport sys,time,json,shutil\nsys.path.insert(0,\'/opt/runner\')\nimport general_copy_catalog as G\nfrom google.auth.exceptions import DefaultCredentialsError\nimport google.auth\ncalls=[]\ndef refuse(*args,**kwargs):\n calls.append(True)\n raise DefaultCredentialsError(\'OFFLINE_REFUSAL\')\ngoogle.auth.default=refuse\nstart=time.monotonic()\nb={\'source_root\':\'/opt/omi\',\'git_path\':shutil.which(\'git\'),\'target_host\':\'192.0.2.8\',\'database\':\'synthetic\',\'current_role\':\'synthetic\',\'target_port\':5432}\nG.verify_source(b,start+40)\ntry:G.connect_workload(b)\nexcept DefaultCredentialsError:pass\nelse:raise ValueError(\'CREDENTIAL_REFUSAL_REQUIRED\')\nif calls!=[True]:raise ValueError(\'EXACT_ONE_ADC_REFUSAL_REQUIRED\')\nprint(json.dumps({\'full_working_blob_check\':True,\'ignored_file_check\':True,\'credential_refusal_injected\':True,\'real_credentials_used\':False,\'sql_called\':False,\'elapsed_ms\':round((time.monotonic()-start)*1000)}))\n"""\nstart=time.monotonic();outcome,raw=process_guard.run_group([sys.executable,\'-I\',\'-B\',\'-c\',child],timeout=60)\nif outcome!={\'result\':\'COMPLETED\',\'exit_code\':0}:raise ValueError(\'SOURCE_OR_GUARD_REFUSAL_FAILED\')\nreport=json.loads(raw)\nexpected_fields={\'full_working_blob_check\':True,\'ignored_file_check\':True,\'credential_refusal_injected\':True,\'real_credentials_used\':False,\'sql_called\':False}\nif set(report)!=set(expected_fields)|{\'elapsed_ms\'} or any(type(report[k]) is not type(v) or report[k]!=v for k,v in expected_fields.items()) or type(report[\'elapsed_ms\']) is not int or not 0<=report[\'elapsed_ms\']<40000:raise ValueError(\'FULL_SOURCE_DEADLINE_OR_RECEIPT\')\nprint(json.dumps(dict(report,result=\'GENERAL_COPY_SOURCE_CHECKS_REACHED_CREDENTIAL_REFUSAL\',catalog_sha256=expected,uid=1000)))\n'


def source_refusal_program(expected_sha):
    if expected_sha != P.CATALOG_SHA:
        raise ValueError('EXACT_CATALOG_PROFILE_SHA_REQUIRED')
    return SOURCE_REFUSAL_PROGRAM.replace('__CATALOG_SHA256__', expected_sha)


def validate_source_refusal(report, expected_sha):
    source_refusal_program(expected_sha)
    expected = {
        'result': 'GENERAL_COPY_SOURCE_CHECKS_REACHED_CREDENTIAL_REFUSAL',
        'catalog_sha256': expected_sha,
        'uid': 1000,
        'full_working_blob_check': True,
        'ignored_file_check': True,
        'credential_refusal_injected': True,
        'real_credentials_used': False,
        'sql_called': False,
    }
    if (
        not isinstance(report, dict)
        or set(report) != set(expected) | {'elapsed_ms'}
        or any(not P.exact(report.get(k), v) for k, v in expected.items())
        or type(report.get('elapsed_ms')) is not int
        or not 0 <= report['elapsed_ms'] < 40000
    ):
        raise ValueError('REAL_FULL_SOURCE_CATALOG_REFUSAL_REQUIRED')
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
