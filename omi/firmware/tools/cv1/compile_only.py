"""Compile application objects only, with supported NCS skip-build/signing options.
Produces only static archives/objects; no update, firmware image or hardware operation.
"""
import hashlib,json,os,signal,stat,subprocess,uuid
from pathlib import Path
BASELINE='e86cda5abb0ea7ff942ac1bcd07261140953812c'
PROFILE='''# COMPILE VALIDATION ONLY. Never flash or release outputs.
CONFIG_BOOTLOADER_MCUBOOT=y
CONFIG_MCUBOOT_BUILD_STRATEGY_SKIP_BUILD=y
CONFIG_SIGN_IMAGES=n
CONFIG_BOOT_SIGNATURE_KEY_FILE=""
CONFIG_MCUBOOT_SIGNATURE_KEY_FILE=""
CONFIG_MCUBOOT_ENCRYPTION_KEY_FILE=""
CONFIG_MCUBOOT_GENERATE_UNSIGNED_IMAGE=n
CONFIG_MCUBOOT_BOOTLOADER_MODE_OVERWRITE_ONLY=y
CONFIG_MCUBOOT_HARDWARE_DOWNGRADE_PREVENTION=n
CONFIG_SECURE_BOOT=n
CONFIG_NCS_INCLUDE_RPMSG_CHILD_IMAGE=n
CONFIG_BUILD_OUTPUT_BIN=n
CONFIG_BUILD_OUTPUT_HEX=n
'''
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def source_allowed(name):
 p=Path(name)
 return not p.is_absolute() and '..' not in p.parts and (name.startswith('omi/firmware/omi/') or name.startswith('omi/firmware/boards/')) and p.suffix.lower() not in ('.pem','.key','.hex','.bin','.zip','.elf') and p.name not in ('id_rsa','id_ed25519') and '/flash_' not in name.lower()
def select_source_names(tracked,untracked):
 return sorted(set([n for n in tracked if source_allowed(n)]+[n for n in untracked if source_allowed(n) and Path(n).suffix.lower() in ('.c','.h')]))
def snapshot_active_source(repo,destination,names):
 """Copy explicit active source bytes once; exclude untracked configs and key trees upstream."""
 repo=Path(repo).resolve();destination=Path(destination);records=[]
 for name in sorted(set(names)):
  if not source_allowed(name):raise ValueError('disallowed compile source')
  source=repo/name
  if repo not in source.resolve().parents:raise ValueError('source escapes checkout')
  if any((repo/Path(*Path(name).parts[:i])).is_symlink() for i in range(1,len(Path(name).parts)+1)):raise ValueError('source symlink rejected')
  fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
  try:
   before=os.fstat(fd)
   if not stat.S_ISREG(before.st_mode) or before.st_size>8*1024*1024:raise ValueError('bounded regular source required')
   data=b''
   while len(data)<=8*1024*1024:
    chunk=os.read(fd,min(65536,8*1024*1024+1-len(data)))
    if not chunk:break
    data+=chunk
   after=os.fstat(fd)
   if len(data)!=before.st_size or (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('source changed during snapshot')
  finally:os.close(fd)
  target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
  records.append(dict(path=name,sha256=hashlib.sha256(data).hexdigest()))
 return records
def validate_config(text):
 forbidden=['CONFIG_SECURE_BOOT=y','CONFIG_NCS_INCLUDE_RPMSG_CHILD_IMAGE=y','CONFIG_MCUBOOT_GENERATE_UNSIGNED_IMAGE=y','CONFIG_BUILD_OUTPUT_BIN=y','CONFIG_BUILD_OUTPUT_HEX=y','CONFIG_SIGN_IMAGES=y','CONFIG_MCUBOOT_BUILD_STRATEGY_FROM_SOURCE=y','CONFIG_BOOTLOADER_PROVISION_HEX=y']
 required=['CONFIG_BOOT_SIGNATURE_KEY_FILE=""','CONFIG_MCUBOOT_BUILD_STRATEGY_SKIP_BUILD=y']
 if any(x in text.splitlines() for x in forbidden) or any(x not in text.splitlines() for x in required):raise ValueError('compile-only config enables image/key/child behavior or lacks skip strategy')
def validate_commands(text):
 for marker in ['keygen.py','imgtool.py','west sign','provision.py','PRIVATE.pem','root-rsa-2048.pem']:
  if marker in text:raise ValueError('signing/provision/key command in compile graph:'+marker)
def build_application_objects(config,kit,work_root):
 kit=Path(kit);root=Path(work_root);repo=Path(config['checkout_root']);sdk=Path(config['sdk_root']);tc=Path(config['toolchain_root'])
 run=root/('compile-only-'+uuid.uuid4().hex);run.mkdir(mode=0o700)
 state=dict(state='preparing',hardware_access=False,key_files_copied=False,signing_enabled=False,flashable=False,releasable=False,full_firmware_build=False,source_revision=BASELINE,run_path=str(run))
 def save():(run/'BUILD-ONLY-NOT-FLASHABLE.json').write_text(json.dumps(state,indent=2)+'\n')
 def command(name,args,cwd=None,env=None,timeout=120):
  with (run/(name+'.stdout')).open('xb') as stdout,(run/(name+'.stderr')).open('xb') as stderr:
   proc=subprocess.Popen(args,cwd=cwd,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
   try:code=proc.wait(timeout=timeout)
   except subprocess.TimeoutExpired:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=2)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=2)
    raise RuntimeError(name+' timeout')
  (run/(name+'.json')).write_text(json.dumps(dict(command=args,returncode=code),indent=2)+'\n')
  if code:raise RuntimeError(name+' failed; inspect bounded local logs')
  return (run/(name+'.stdout')).read_bytes()
 try:
  head=command('01-source-head',['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()
  if head!=BASELINE:command('01b-source-ancestry',['git','-C',str(repo),'merge-base','--is-ancestor',BASELINE,head])
  state['source_revision']=head
  names=command('02-source-list',['git','-C',str(repo),'ls-files','-z','--cached','--','omi/firmware/omi','omi/firmware/boards']).decode().strip('\0').split('\0')
  extra=command('02b-untracked-source',['git','-C',str(repo),'ls-files','-z','--others','--exclude-standard','--','omi/firmware/omi','omi/firmware/boards']).decode().strip('\0').split('\0')
  selected=select_source_names(names,extra)
  if not selected:raise ValueError('no allowed tracked compile source')
  source=run/'source';source.mkdir()
  records=snapshot_active_source(repo,source,selected);manifest=run/'03-active-source.json';manifest.write_text(json.dumps(records,indent=2)+'\n')
  overlay=run/'compile-only.conf';overlay.write_text(PROFILE);lock=json.loads((kit/'checkout-dependencies.lock.json').read_text())
  if sha(tc/'environment.json')!=lock['toolchain_environment_sha256']:raise ValueError('toolchain environment changed')
  env=os.environ.copy()
  for item in json.loads((tc/'environment.json').read_text())['env_vars']:
   if item['type']=='relative_paths':
    value=os.pathsep.join(str(tc/p) for p in item['values'])
    if item.get('existing_value_treatment')=='prepend_to':value+=os.pathsep+env.get(item['key'],'')
   else:value=item['value']
   env[item['key']]=value
  env.update(ZEPHYR_BASE=str(sdk/'zephyr'),XDG_CACHE_HOME=str(run/'cache'),ZEPHYR_BASE_CACHE=str(run/'cache'),CCACHE_DISABLE='1',PYTHONDONTWRITEBYTECODE='1')
  fw=source/'omi/firmware';build=run/'build';state['state']='configuring';save()
  command('06-configure',[str(tc/'bin/cmake'),'-S',str(fw/'omi'),'-B',str(build),'-GNinja','-DBOARD=omi/nrf5340/cpuapp','-DBOARD_ROOT='+str(fw),'-DCONF_FILE=omi.conf','-DEXTRA_CONF_FILE='+str(overlay),'-DPM_STATIC_YML_FILE='+str(kit/'pinned-partitions.yml'),'-DUSER_CACHE_DIR='+str(run/'cache'),'-DFETCHCONTENT_FULLY_DISCONNECTED=ON','-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF'],cwd=sdk,env=env)
  validate_config((build/'zephyr/.config').read_text())
  commands=command('07-inspect-app-graph',[str(tc/'bin/ninja'),'-C',str(build),'-t','commands','app'],env=env).decode();validate_commands(commands)
  state['state']='compiling_application_objects';save();command('08-compile-app',[str(tc/'bin/cmake'),'--build',str(build),'--target','app','--','-j4'],env=env,timeout=180)
  lib=build/'app/libapp.a'
  if not lib.is_file():raise ValueError('application archive missing')
  images=[p for p in build.rglob('*') if p.is_file() and (p.suffix.lower() in ('.pem','.key','.hex','.bin','.elf') or p.name=='dfu_application.zip')]
  if images:raise ValueError('unexpected key/image output; quarantine run')
  state.update(state='completed_compile_only',source_manifest_sha256=sha(manifest),application_library_sha256=sha(lib),configuration_sha256=sha(build/'zephyr/.config'),command_graph_sha256=sha(run/'07-inspect-app-graph.stdout'),no_firmware_images=True)
 except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as ex:state.update(state='stopped',error=str(ex))
 finally:save()
 return state
