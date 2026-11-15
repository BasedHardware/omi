#!/usr/bin/env python3
"""Compile and run the exact reviewed shared C helpers using synthetic inputs."""
import argparse,json,os,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cc',default=os.environ.get('CC','cc'));p.add_argument('--sanitizer',choices=['none','undefined','address,undefined'],default='none');a=p.parse_args()
firmware=Path(__file__).resolve().parents[2]
root=firmware/'omi/src/lib/core'
test=firmware/'omi/tests/host/audio_packet_logic_test.c'
with tempfile.TemporaryDirectory(prefix='cv1-shared-c-') as d:
 binary=str(Path(d)/'host-test');cmd=[a.cc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-pedantic']
 if a.sanitizer!='none':cmd+=['-g','-fsanitize='+a.sanitizer,'-fno-sanitize-recover=all']
 cmd+=['-I.', 'audio_packet_logic.c',str(test),'-o',binary]
 results=[]
 for label,command in [('compile',cmd),('execute',[binary])]:
  try:
   q=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=30)
   results.append({'stage':label,'returncode':q.returncode,'stdout':q.stdout,'stderr':q.stderr})
   if q.returncode:break
  except subprocess.TimeoutExpired as e:
   results.append({'stage':label,'state':'timeout','limit_seconds':30,'stdout':(e.stdout or b'').decode(errors='replace'),'stderr':(e.stderr or b'').decode(errors='replace')});break
  except OSError as e:
   results.append({'stage':label,'state':'os_error','error':str(e)});break
 print(json.dumps({'sanitizer':a.sanitizer,'parameter_iterations':222745,'layer':'shared C host checks, not emulation or device qualification','results':results},indent=2))
 raise SystemExit(any(x.get('returncode',1) for x in results))
