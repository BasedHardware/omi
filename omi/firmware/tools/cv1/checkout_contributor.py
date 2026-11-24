"""Checkout-aware no-jig targets. No installs/fetches, key access or hardware probes.
Full sysbuild execution is intentionally unavailable in this key-free stage.
"""
import concurrent.futures,hashlib,json,os,shutil,stat,subprocess,sys
from pathlib import Path
BASELINE='e86cda5abb0ea7ff942ac1bcd07261140953812c'
EXCLUDES=[':(exclude,glob)**/*.pem',':(exclude,glob)**/*.key',':(exclude,glob)**/id_rsa',':(exclude,glob)**/id_ed25519']
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(65536),b''):h.update(b)
 return h.hexdigest()
def config(path):
 p=Path(path)
 if p.suffix!='.json':raise ValueError('configuration must be an explicit JSON file')
 fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  st=os.fstat(fd)
  if not stat.S_ISREG(st.st_mode) or st.st_size>65536:raise ValueError('bounded regular config required')
  b=b''
  while len(b)<=65536:
   chunk=os.read(fd,65537-len(b))
   if not chunk:break
   b+=chunk
  after=os.fstat(fd)
  if len(b)!=st.st_size or (st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('config changed while reading')
 finally:os.close(fd)
 text=b.decode();depth=0;quote=False;escape=False
 for c in text:
  if quote:
   if escape:escape=False
   elif c=='\\':escape=True
   elif c=='"':quote=False
  elif c=='"':quote=True
  elif c in '[{':
   depth+=1
   if depth>8:raise ValueError('config nesting bound')
  elif c in ']}':depth-=1
 def pairs(items):
  d={}
  for k,v in items:
   if k in d:raise ValueError('duplicate config field')
   d[k]=v
  return d
 value=json.loads(text,object_pairs_hook=pairs)
 allowed={'schema','checkout_root','compiler','sdk_root','toolchain_root'}
 if type(value) is not dict or not {'schema','checkout_root','compiler'}<=set(value)<=allowed or type(value['schema']) is not int or value['schema']!=1:raise ValueError('config schema/unknown fields')
 for key in allowed-{'schema'}:
  if key in value and (type(value[key]) is not str or not value[key] or len(value[key])>4096):raise ValueError('bounded config string required:'+key)
 return value,hashlib.sha256(b).hexdigest()
def metadata_git(root,args):
 command=['git','--no-pager','-c','core.fsmonitor=false','-C',str(root)]+args
 try:
  q=subprocess.run(command,capture_output=True,text=True,timeout=10)
  return q.returncode,q.stdout.strip()
 except (OSError,subprocess.TimeoutExpired):return None,''
def source_check(root,expected=BASELINE):
 p=Path(root).resolve()
 if 'upstream-keep-clean' in p.parts:return dict(state='failed',reason='shared object store is not a task checkout')
 code,head=metadata_git(p,['rev-parse','HEAD'])
 if code!=0:return dict(state='unavailable',reason='Git checkout unavailable; no clone/fetch attempted')
 if head!=expected:
  code,_=metadata_git(p,['merge-base','--is-ancestor',expected,head])
  if code!=0:
   code,shallow=metadata_git(p,['rev-parse','--is-shallow-repository'])
   if code==0 and shallow=='true':return dict(state='failed',reason='shallow clone: baseline ancestry unreachable until git fetch --unshallow (run outside this tool; no fetch attempted)',expected=expected,observed=head)
   return dict(state='failed',reason='unsupported baseline ancestry',expected=expected,observed=head)
 code,_=metadata_git(p,['diff','--quiet','--no-ext-diff','--no-textconv','HEAD','--','omi/firmware']+EXCLUDES)
 return dict(state='passed' if code in (0,1) else 'unavailable',revision=head,tracked_firmware_changes=code==1,reason='supported baseline ancestry; active non-key firmware changes are test inputs, not rejected; untracked config untouched')
def sdk_check(root,lock):
 base=Path(root)
 if not base.is_dir():return dict(state='unavailable',reason='SDK directory missing; no west init/update attempted')
 def one(item):
  code,head=metadata_git(base/item['path'],['rev-parse','HEAD'])
  if code!=0:return dict(project=item['name'],state='unavailable')
  if head!=item['commit']:return dict(project=item['name'],state='failed',reason='SDK commit mismatch')
  code,_=metadata_git(base/item['path'],['diff','--quiet','--no-ext-diff','--no-textconv','HEAD','--','.']+EXCLUDES)
  if code not in (0,1):return dict(project=item['name'],state='unavailable')
  if code==1:return dict(project=item['name'],state='failed',reason='SDK tracked source mismatch')
  for label,extra in (('untracked',[]),('ignored',['--ignored'])):
   code,out=metadata_git(base/item['path'],['ls-files','-z','--others','--exclude-standard']+extra+['--','.']+EXCLUDES)
   if code!=0:return dict(project=item['name'],state='unavailable')
   stray=[x for x in out.split('\0') if x and not (x.endswith('.pyc') and '__pycache__' in x.split('/'))]
   if stray:return dict(project=item['name'],state='failed',reason='SDK project has '+label+' files; pinned projects must match the reference checkout exactly')
  return dict(project=item['name'],state='passed')
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,lock['sdk_projects']))
 state='passed' if all(x['state']=='passed' for x in rows) else 'failed' if any(x['state']=='failed' for x in rows) else 'unavailable'
 return dict(state=state,projects=rows,declared_but_absent_reference_projects=dict(state='skipped',count=len(lock['not_cloned_in_reference']),reason='not in prior successful CV1 workspace; not a complete hermetic SDK freeze'),key_files_inspected=False)
def toolchain_check(root,lock):
 tc=Path(root)
 if not tc.is_dir():return dict(state='unavailable',reason='Pinned toolchain missing; no installation attempted')
 try:
  if digest(tc/'environment.json')!=lock['toolchain_environment_sha256']:return dict(state='failed',reason='toolchain environment hash mismatch')
  for item in lock['toolchain_files']:
   if digest(tc/item['public_path'])!=item['sha256']:return dict(state='failed',reason='public tool binary/script hash mismatch:'+item['public_path'])
 except OSError:return dict(state='unavailable',reason='required public tool file unavailable')
 for tool in ('bin/cmake','bin/ninja'):
  try:q=subprocess.run([str(tc/tool),'--version'],capture_output=True,text=True,timeout=10)
  except (OSError,subprocess.TimeoutExpired):return dict(state='failed',reason='pinned tool executable failed to launch:'+tool)
  if q.returncode!=0:return dict(state='failed',reason='pinned tool executable failed self-check:'+tool)
 return dict(state='passed',toolchain_id=lock['toolchain_id'],reason='existing public tool files match pinned profile and pinned CMake/Ninja executables launch; no key/package installation probe')
def host_prerequisite():
 if sys.version_info<(3,9):return dict(state='unavailable',reason='Python3.9 or newer required; no install attempted')
 if sys.platform=='darwin':
  try:
   q=subprocess.run(['/usr/bin/xcode-select','-p'],capture_output=True,text=True,timeout=5)
   if q.returncode!=0:return dict(state='unavailable',reason='Command Line Tools absent; no compiler/Git stub invoked and no installer requested')
  except (OSError,subprocess.TimeoutExpired):return dict(state='unavailable',reason='Command Line Tools readiness unknown; no install attempted')
 return dict(state='passed',reason='Python/host tool readiness; no installer invoked')
def kit_integrity(kit):
 try:q=subprocess.run([sys.executable,str(kit/'verify_manifest.py')],capture_output=True,text=True,timeout=10)
 except (OSError,subprocess.TimeoutExpired):return dict(state='unavailable',reason='kit integrity command unavailable')
 return dict(state='passed' if q.returncode==0 else 'failed',reason='existing manifest verification')
def run(action,config_path,kit,work_root=None):
 kit=Path(kit);result=dict(schema=1,target=action,hardware_access=False,signing_keys_accessed=False,install_or_fetch_attempted=False,release_authorized=False,stages=[])
 def add(name,state,required=False,**data):result['stages'].append(dict(name=name,state=state,required=required,**data))
 try:
  if config_path is None and action=='quick-host':
   c=dict(schema=1,checkout_root=str(kit.parents[3]),compiler='cc');ch=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()
  else:c,ch=config(config_path)
  result['config_sha256']=ch
 except (OSError,ValueError,TypeError,RecursionError) as ex:
  add('configuration','failed',True,reason=str(ex));result['required_stages_passed']=False;return result
 if action=='quick-host' and Path(c['checkout_root']).resolve()!=kit.resolve().parents[3]:
  add('checkout_selection','failed',True,reason='quick-host config must select the checkout containing this entrypoint; refusing to attribute tests to another checkout');result['required_stages_passed']=False;return result
 host=host_prerequisite();add('host_prerequisite',required=True,**host)
 if host['state']!='passed':result['required_stages_passed']=False;return result
 source=source_check(c['checkout_root']);add('source',required=True,**source)
 add('hardware','skipped',reason='no-jig target: no USB, serial, BLE or debugger enumeration attempted')
 if source['state']!='passed':result['required_stages_passed']=False;return result
 if action=='quick-host':
  compiler=shutil.which(c['compiler'])
  add('C11_UBSan_compiler','passed' if compiler else 'unavailable',True,reason='compiler discovered; compilation validated by existing host checks' if compiler else 'compiler missing; no installation attempted')
  add('Nordic_SDK','skipped',reason='not required for quick host checks')
  add('firmware_build','skipped',reason='separate target; not counted as host coverage')
  if compiler:
   from contributor import verify
   receipt=verify(kit,compiler);add('existing_host_checks','passed' if receipt['passed'] else 'failed',True,receipt=receipt,source_scope='active monorepo shared C packet helpers plus offline models/replays; not a Zephyr runtime emulator')
 elif action in ('firmware-build','compile-only'):
  integrity=kit_integrity(kit);add('kit_integrity',required=True,**integrity)
  if integrity['state']!='passed':result['required_stages_passed']=False;return result
  lock=json.loads((kit/'checkout-dependencies.lock.json').read_text())
  add('Nordic_SDK',required=True,**(sdk_check(c['sdk_root'],lock) if 'sdk_root' in c else dict(state='unavailable',reason='sdk_root not configured')))
  add('toolchain',required=True,**(toolchain_check(c['toolchain_root'],lock) if 'toolchain_root' in c else dict(state='unavailable',reason='toolchain_root not configured')))
  add('partition_map','passed' if digest(kit/'pinned-partitions.yml')==lock['static_partition_sha256'] else 'failed',True)
  if action=='compile-only':
   if not all(x['state']=='passed' for x in result['stages'] if x['required']) or work_root is None:
    add('application_compile_only','blocked',True,reason='existing pinned dependencies and explicit output directory required')
   else:
    from compile_only import build_application_objects
    receipt=build_application_objects(c,kit,work_root);add('application_compile_only','passed' if receipt['state']=='completed_compile_only' else 'failed',True,receipt=receipt)
   result['required_stages_passed']=all(x['state']=='passed' for x in result['stages'] if x['required']);return result
  add('firmware_build','blocked',True,reason='baseline sysbuild performs MCUboot/NSIB key operations; key-free stage does not execute signing or open/generate keys',historical_build='Historical bench build evidence is outside this source tree; this is not a new build')
  result['reviewed_build_plan']=['<toolchain>/bin/west','build','-b',lock['board'],'<tracked-snapshot>/omi/firmware/omi','--sysbuild','-d','<unique-build-dir>','--pristine','always','-o=-j4','--','-DBOARD_ROOT=<tracked-snapshot>/omi/firmware','-DPM_STATIC_YML_FILE=<kit>/pinned-partitions.yml']
  result['build_executed']=False
 else:raise ValueError('unknown contributor target')
 result['required_stages_passed']=all(x['state']=='passed' for x in result['stages'] if x['required']);return result
