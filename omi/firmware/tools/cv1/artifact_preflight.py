"""Offline compatibility checks. No device commands, signature verification or release authority.
Only exact reviewed baseline restoration is eligible for full/network SWD writes.
New network images remain blocked pending independent signed-image review.
"""
import argparse, hashlib, json
from pathlib import Path

def digest(data): return hashlib.sha256(data).hexdigest()
def strict_json(data):
    if len(data)>4*1024*1024:raise ValueError('JSON input exceeds4MiB')
    text=data.decode('utf-8');depth=0;quoted=False;escaped=False
    for char in text:
        if quoted:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
        elif char=='"':quoted=True
        elif char in '[{':
            depth+=1
            if depth>64:raise ValueError('JSON nesting exceeds64')
        elif char in ']}':depth-=1
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('duplicate JSON field '+key)
            result[key]=value
        return result
    def constant(value):raise ValueError('non-JSON numeric constant '+value)
    try:return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)
    except RecursionError as ex:raise ValueError('JSON parser recursion bound') from ex
def validation_capabilities(contract):
    """Interpret externally pinned configuration evidence, never verify image signatures.

    Provision records are metadata unless the selected validation branch authenticates
    against them. Unsupported or insufficiently evidenced modes remain unknown.
    """
    evidence=contract.get('validation_policy',{})
    result={}
    for role,modes in [('application',{'rsa_pss_2048_sha256':'signature'}),
                       ('network',{'sha256_hash_only':'integrity_only','ecdsa_p256_sha256_signature':'signature'})]:
        item=evidence.get(role,{}) if type(evidence) is dict else {}
        valid=type(item) is dict and set(item)=={'mode','config_sha256','implementation_sha256','installed_image_evidence_sha256'}
        if valid:
            valid=all(type(item[f]) is str and len(item[f])==64 and all(c in '0123456789abcdef' for c in item[f]) for f in ('config_sha256','implementation_sha256','installed_image_evidence_sha256'))
        mode=item.get('mode') if type(item) is dict else None
        if not valid or type(mode) is not str or mode not in modes:
            result[role]={'mode':'unknown','enforcement':'unknown','configuration_and_installed_image_evidence_complete':False}
        else:
            result[role]={'mode':mode,'enforcement':modes[mode],'configuration_and_installed_image_evidence_complete':True}
    result['image_signature_verification_performed']=False
    result['scope']='Externally pinned retained-build and saved-readback evidence; not fresh hardware or cryptographic verification.'
    return result
def manifest_schema(m):
    allowed={'schema','operation','board','layout_sha256','baseline_contract_sha256','images','version_policy','dependency_evidence','signature_verification_evidence','pinned_client_confirmation_evidence','overwrite_recovery_plan'}
    if type(m) is not dict or set(m)-allowed or type(m.get('schema')) is not int or m['schema']!=1:
        raise ValueError('manifest schema/version/unknown fields rejected')
    for field in ('operation','board','layout_sha256','baseline_contract_sha256'):
        if type(m.get(field)) is not str or not 1<=len(m[field])<=128:raise ValueError('manifest requires bounded string '+field)
    if type(m.get('images')) is not list or len(m['images'])>2:raise ValueError('images must be an explicit list of at most two roles')
    for image in m['images']:
        if type(image) is not dict or set(image)-{'role','file','sha256','public_key'}:raise ValueError('image unknown fields/type rejected')
        for field in ('role','file','sha256'):
            if type(image.get(field)) is not str or not 1<=len(image[field])<=512:raise ValueError('image requires bounded string '+field)
        if 'public_key' in image:
            key=image['public_key']
            if type(key) is not dict or set(key)-{'file','sha256','role'}:raise ValueError('public key evidence unknown fields/type')
            if 'role' in key and key['role']!='public':raise ValueError('public key evidence role')
            if any(type(key.get(f)) is not str or not key[f] for f in ('file','sha256')):raise ValueError('public key evidence requires string path/hash')
    for field in allowed-{'schema','operation','board','layout_sha256','baseline_contract_sha256','images'}:
        if field in m and (type(m[field]) is not str or not m[field] or len(m[field])>4096):raise ValueError('proposed gate declaration must be a bounded evidence string: '+field)

def hex_bytes(data):
    memory={}; upper=0; ended=False
    for line in data.decode('ascii').splitlines():
        if not line.startswith(':'): raise ValueError('invalid Intel HEX record')
        row=bytes.fromhex(line[1:])
        if len(row)<5 or row[0]+5!=len(row) or sum(row)%256: raise ValueError('invalid HEX length/checksum')
        size,address,kind=row[0],int.from_bytes(row[1:3],'big'),row[3]; body=row[4:-1]
        if ended: raise ValueError('data after EOF')
        if kind==0:
            for i,b in enumerate(body):
                a=upper+address+i
                if a in memory: raise ValueError('overlapping HEX data')
                memory[a]=b
        elif kind==4 and size==2 and address==0: upper=int.from_bytes(body,'big')<<16
        elif kind==1 and size==0: ended=True
        elif kind in (3,5) and size==4: pass
        else: raise ValueError('unsupported HEX record')
    if not ended or not memory: raise ValueError('missing EOF or empty image')
    return memory

def evaluate(manifest_path, contract_path):
    errors=[]
    def reject(code,reason,category='compatibility'): errors.append(dict(code=code,reason=reason,category=category))
    manifest_path=Path(manifest_path); contract_path=Path(contract_path)
    manifest_bytes=manifest_path.read_bytes(); contract_bytes=contract_path.read_bytes()
    c=strict_json(contract_bytes); m=strict_json(manifest_bytes); manifest_schema(m)
    def blob(entry):
        p=(manifest_path.parent/entry['file']).resolve()
        if manifest_path.parent.resolve() not in p.parents: raise ValueError('artifact must be below manifest directory')
        b=p.read_bytes()
        if digest(b)!=entry['sha256']: raise ValueError('artifact hash mismatch: '+entry['file'])
        return b
    if m.get('schema')!=1: reject('schema','Use explicit preflight manifest schema 1; legacy artifact manifests are not approvals.')
    if m.get('baseline_contract_sha256')!=digest(contract_bytes): reject('baseline','Bind the exact reviewed baseline contract hash.')
    if m.get('board')!=c['board']: reject('board','Board must match the qualified CV1 board contract.')
    if m.get('layout_sha256')!=c['layout_sha256']: reject('layout','Use the pinned partition layout; dynamic layout changes require review.')
    validation=validation_capabilities(c)
    for role in ('application','network'):
        if validation[role]['mode']=='unknown': reject(role+'_validation_unknown','Missing or unsupported '+role+' enforcement mode/configuration/installed-image evidence. Compatibility remains unknown.')
    observations=[]
    installed=c.get('installed_provision',{})
    if type(installed) is not dict:installed={}
    if not installed.get('verified_readback_sha256') or not installed.get('public_records') or not installed.get('receipt_sha256'): reject('trust_unknown','Installed public provision evidence is missing; obtain verified readback evidence.')
    mode=m.get('operation'); images=m.get('images',[]); roles=[i.get('role') for i in images]
    expected={'reviewed_swd_app_only':['application'], 'reviewed_swd_baseline_restore':['application_full','network_full'], 'proposed_ota_pair':['application','network']}
    if mode not in expected or sorted(roles)!=sorted(expected.get(mode,[])): reject('roles','Declare one unambiguous supported operation and its exact image roles.')
    for image in images:
        try:
            b=blob(image); role=image.get('role'); h=digest(b)
            if role=='application' and mode=='reviewed_swd_app_only':
                mem=hex_bytes(b)
                if min(mem)<0x10000 or max(mem)>=0xf6000: reject('app_range','App-only HEX must exclude MCUboot, provision, network and persistence.')
                # Closed allow-list: a claimed review flag alone cannot authorize new bytes.
                if h not in c.get('reviewed_app_only_sha256',[]): reject('app_review','Exact application hash has no independent hardware-configuration review in this contract.')
            if role in ('network','network_full'):
                evidence=image.get('public_key')
                if not evidence: reject('network_trust_unknown','Supply public raw P-256 key evidence bound to the image; never private keys.')
                else:
                    key=blob(evidence)
                    payload=bytes(v for _,v in sorted(hex_bytes(b).items())) if b.startswith(b':') else b
                    if len(key)!=64 or key not in payload: reject('network_key_evidence','Public key must be the 64-byte raw key present in the reviewed network image.')
                    else:
                        matches=digest(key)[:32] in [r['hash16'] for r in installed.get('public_records',[]) if r.get('valid')]
                        observations.append(dict(role=role,public_key_sha256=digest(key),matches_installed_provision_metadata=matches,enforcement=validation['network']['enforcement'],signature_rejection_proven=False))
                        if not matches and validation['network']['enforcement']=='signature':
                            reject('network_signature_trust_mismatch','Selected authenticated validation mode lacks matching installed public trust metadata; signature acceptance is unproven. No signature verification was performed.')
                if h!=c['baseline_images'].get('network_full'): reject('network_review','New network bytes lack exact-baseline compatibility review. Hash-only metadata differences do not prove signature rejection; outer MCUboot authentication/update compatibility still requires qualification.')
            if mode=='reviewed_swd_baseline_restore' and h!=c['baseline_images'].get(role): reject('restore_hash','Restore accepts only exact reviewed baseline images, not a new full build.')
        except (OSError,ValueError,KeyError,UnicodeError) as ex: reject('artifact',str(ex))
    if mode=='proposed_ota_pair':
        # These are proposed local release gates, NOT claims about shipping product policy.
        for field in ('version_policy','dependency_evidence','signature_verification_evidence','pinned_client_confirmation_evidence','overwrite_recovery_plan'):
            if not m.get(field): reject(field,'Missing '+field+'; current product capability does not establish this proposed gate.','proposed_release_gate')
        reject('ota_not_qualified','OTA execution is disabled: overwrite-only baseline has no automatic old-image revert; independent BLE/interrupt qualification is incomplete.','proposed_release_gate')
    return dict(schema=1,eligible_for_live_identity_gate=not errors,hardware_authorized=False,manifest_sha256=digest(manifest_bytes),validated_operation=mode,baseline_contract_sha256=digest(contract_bytes),errors=errors,current_capabilities=c['current_capabilities'],validation_capabilities=validation,network_metadata_observations=observations,limitations=['Offline evidence is not a live target identity check or cryptographic signature verification.','Hash-only network validation does not authenticate provisioned public keys; metadata mismatch alone does not establish rejection.','Application MCUboot RSA-PSS verification is separate from network b0n hash validation; outer update acceptance is not tested here.','SWD restoration is not OTA rollback. No device operation is implemented here.'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest');p.add_argument('--contract',required=True);a=p.parse_args()
    try: result=evaluate(a.manifest,a.contract)
    except (OSError,ValueError,KeyError,TypeError,RecursionError) as ex: result={'eligible_for_live_identity_gate':False,'hardware_authorized':False,'errors':[{'code':'invalid_input','reason':str(ex)}]}
    print(json.dumps(result,indent=2));return 0 if result['eligible_for_live_identity_gate'] else 2
if __name__=='__main__': raise SystemExit(main())
