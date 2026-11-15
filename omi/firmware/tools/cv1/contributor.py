#!/usr/bin/env python3
"""Host/application-object checks. No images/install/fetch/key/target/release execution."""
import argparse,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path

def verify(root,cc):
    commands=[[sys.executable,'verify_manifest.py'],[sys.executable,'-m','unittest','-v'],[sys.executable,'run_shared_c.py','--cc',cc],[sys.executable,'run_shared_c.py','--cc',cc,'--sanitizer','undefined']]
    runs=[]
    for command in commands:
        try:
            p=subprocess.run(command,cwd=root,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=120)
            runs.append(dict(command=command,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        except (subprocess.TimeoutExpired,OSError) as ex:
            runs.append(dict(command=command,returncode=None,error=type(ex).__name__))
        if runs[-1]['returncode']!=0:break
    return dict(schema=1,layer='offline host checks',hardware_used=False,release_authorized=False,passed=len(runs)==len(commands) and all(r['returncode']==0 for r in runs),runs=runs)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['verify','quick-host','firmware-build','compile-only']);p.add_argument('--cc',default='cc');p.add_argument('--config');p.add_argument('--output',required=True);a=p.parse_args()
    out=Path(a.output)
    if out.exists():p.error('Refusing to truncate an existing evidence file; choose a unique run path.')
    if a.action=='verify':
        r=verify(Path(__file__).resolve().parent,a.cc);passed=r['passed']
    else:
        from checkout_contributor import run
        r=run(a.action,a.config,Path(__file__).resolve().parent,work_root=out.parent);passed=r['required_stages_passed']
    # Exclusive evidence creation; concurrent callers never truncate prior results.
    with out.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
    print(json.dumps(dict(passed=passed,output=str(out),layer=r.get('layer','checkout-aware no-jig prerequisites/host checks'))));return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
