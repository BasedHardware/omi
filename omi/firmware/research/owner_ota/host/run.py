"""Run the local-only C acceptance demo. No installer, BLE, debugger or device path."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--ncs',required=True,type=Path)
    p.add_argument('--mbedcrypto',required=True,type=Path);p.add_argument('--arm-cc',type=Path);p.add_argument('--payload-elf',type=Path)
    p.add_argument('--cc',default='/usr/bin/cc');a=p.parse_args();root=Path(__file__).resolve().parent.parent
    if not a.output.is_absolute() or a.output.exists():raise ValueError('output must be a new absolute directory')
    if root in a.output.resolve().parents:raise ValueError('generated output must be outside source tree')
    if any((parent/'.git').exists() for parent in a.output.resolve().parents):raise ValueError('generated output must be outside all Git checkouts')
    if not a.mbedcrypto.is_file() or not (a.ncs/'modules/crypto/mbedtls/include/psa/crypto.h').is_file():raise ValueError('existing native MbedTLS archive/SDK headers required; no installation attempted')
    if not a.payload_elf and (not a.arm_cc or not a.arm_cc.is_file()):raise ValueError('provide existing --arm-cc or user-built --payload-elf')
    a.ncs=a.ncs.resolve();a.mbedcrypto=a.mbedcrypto.resolve()
    if a.arm_cc:a.arm_cc=a.arm_cc.resolve()
    if a.payload_elf:a.payload_elf=a.payload_elf.resolve()
    from fixtures import build
    a.output.mkdir(parents=True,mode=0o700);out=a.output
    source_paths=[x for x in sorted(root.rglob('*')) if x.is_file() and x.suffix in ('.c','.h','.py','.ld','.md') and '__pycache__' not in x.parts]
    if any(x.is_symlink() for x in source_paths):raise ValueError('source symlinks unsupported')
    inputs={str(x.relative_to(root)):hashlib.sha256(x.read_bytes()).hexdigest() for x in source_paths}
    (out/'source-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
    def command(name,args,timeout=60):
        r=subprocess.run(args,cwd=out,capture_output=True,text=True,timeout=timeout)
        (out/(name+'.json')).write_text(json.dumps({'args':args,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr},indent=2)+'\n')
        if r.returncode:raise RuntimeError(name+' failed; inspect '+str(out/(name+'.json')))
        return r
    payload=a.payload_elf
    if payload is None:
        payload=out/'user-app.elf'
        command('01-user-build',[str(a.arm_cc),'-std=c11','-Os','-g','-mcpu=cortex-m33','-mthumb','-ffreestanding','-fno-builtin','-nostdlib','-Wl,--build-id=none','-Wl,-n','-T',str(root/'host/user_app.ld'),str(root/'host/user_app.c'),'-o',str(payload)])
    fixtures=build(a.ncs,payload,out)
    include=a.ncs/'modules/crypto/mbedtls/include'
    executable=out/'owner-ota-host-demo'
    command('02-host-build',[a.cc,'-std=c11','-O1','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-I'+str(include),'-I'+str(include/'library'),str(root/'shared/secure_image.c'),str(root/'shared/secure_store.c'),str(root/'shared/psa_adapter.c'),str(root/'host/demo.c'),str(a.mbedcrypto),'-o',str(executable)])
    result=command('03-host-demo',[str(executable),str(out/'fixture_registry.public')]+[str(out/(n+'.cv1test')) for n in ('A','B','C','wrong_owner','modified','wrong_ABI')])
    events=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if not events or events[-1]['stage']!='PASS':raise RuntimeError('no terminal C PASS')
    current={str(x.relative_to(root)):hashlib.sha256(x.read_bytes()).hexdigest() for x in source_paths}
    if current!=inputs:raise RuntimeError('source changed during demo')
    report={'schema':1,'passed':True,'layer':'HOST transport/boot/flash simulation with actual sharedC+PSA','transport':'137-byte ordered C stub; notBLE','boot':'explicit outcome stub; notCPUemulation','owner_registry':'public test fixture input only; not enrolled/persistentcredentials','target_operations':False,'production_signing':False,'test_fixture_signing':True,'release_authorized':False,'artifact_admission':False,'source_sha256':hashlib.sha256((out/'source-inputs.json').read_bytes()).hexdigest(),'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),'native_mbedcrypto_sha256':hashlib.sha256(a.mbedcrypto.read_bytes()).hexdigest(),'fixtures_manifest_sha256':hashlib.sha256((out/'fixtures.json').read_bytes()).hexdigest(),'events':events}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'report':str(out/'report.json'),'events':len(events),'target_operations':False}))
if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError,ImportError,subprocess.SubprocessError) as ex:print(str(ex),file=sys.stderr);raise SystemExit(2)
