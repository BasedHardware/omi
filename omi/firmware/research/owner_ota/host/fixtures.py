"""Host fixture producer only; published non-secret NIST keys, no credential input."""
from pathlib import Path
import hashlib,json,re,struct
from cryptography.hazmat.primitives.asymmetric import ec,utils
from cryptography.hazmat.primitives import hashes,serialization
from elftools.elf.elffile import ELFFile
PIN='6401cc102879fcf15b303d97c4f4097d9f874405b121f52717a2e45b7240634e'
DOMAIN=b'CV1-OWNER-APP-v2\0'
ORDER=int('ffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551',16)
def build(ncs,payload_elf,out):
    source=Path(ncs)/'nrf/tests/crypto/test_cases/test_vectors_ecdsa_sign.c'
    if Path(ncs).resolve() not in source.resolve().parents:raise ValueError('test source escapes SDK')
    raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PIN:raise ValueError('unsupported public test-key source; no arbitrary key input')
    text=raw.decode()
    def key(index):
        block=text.split(f'test_vector_ecdsa_sign_secp256r1_SHA256_{index}) = {{',1)[1].split('};',1)[0]
        v={n:re.search(r'\.'+n+r'\s*=\s*"([0-9a-f]+)"',block).group(1) for n in ('p_x','p_qx','p_qy')}
        k=ec.derive_private_key(int(v['p_x'],16),ec.SECP256R1());p=k.public_key().public_numbers()
        if p.x!=int(v['p_qx'],16) or p.y!=int(v['p_qy'],16):raise ValueError('published point mismatch')
        return k
    owner=key(1);wrong=key(2)
    pub=owner.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
    with Path(payload_elf).open('rb') as f:
        elf=ELFFile(f);loads=[p for p in elf.iter_segments() if p['p_type']=='PT_LOAD' and p['p_filesz'] and 0x54200<=p['p_paddr']<0xf0000]
        start=min(p['p_paddr'] for p in loads);end=max(p['p_paddr']+p['p_filesz'] for p in loads)
        if start!=0x54200 or end-start>393216-512:raise ValueError('payload placement/cap')
        payload=bytearray(b'\xff'*(end-start))
        for p in loads:payload[p['p_paddr']-start:p['p_paddr']-start+p['p_filesz']]=p.data()
    network=hashlib.sha256(b'PUBLIC-HOST-DEMO-NETWORK-v1').digest()
    def signed(body,signer=owner,abi=1):
        header=struct.pack('<8I',0x324e574f,2,0x00315643,abi,1,7,len(body),0)+network+hashlib.sha256(body).digest()+hashlib.sha256(pub).digest()
        digest=hashlib.sha256(DOMAIN+header).digest()
        der=signer.sign(digest,ec.ECDSA(utils.Prehashed(hashes.SHA256()),deterministic_signing=True))
        r,s=utils.decode_dss_signature(der);s=min(s,ORDER-s)
        return header+r.to_bytes(32,'big')+s.to_bytes(32,'big')+bytes(320)+body
    # Changed bytes DO NOT imply healthy/fault behavior. Boot outcome is a stub.
    blobs={'A':signed(payload),'B':signed(payload+b'PUBLIC_VARIANT_B'),'C':signed(payload+b'PUBLIC_VARIANT_C')}
    blobs['wrong_owner']=signed(payload+b'WRONG_OWNER',wrong)
    modified=bytearray(blobs['C']);modified[-1]^=1;blobs['modified']=bytes(modified)
    blobs['wrong_ABI']=signed(payload+b'WRONG_ABI',abi=2)
    records={}
    for name,data in blobs.items():
        path=out/(name+'.cv1test');path.write_bytes(data);records[name]={'file':path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'test_only':True}
    policy=struct.pack('<3I',0x00315643,1,7)+network+pub
    (out/'fixture_registry.public').write_bytes(policy)
    result={'schema':1,'host_only':True,'release_authorized':False,'public_test_key_source_sha256':PIN,'owner_public_fingerprint':hashlib.sha256(pub).hexdigest(),'private_key_persisted':False,'production_keys_used':False,'domain_hex':DOMAIN.hex(),'signed_bytes':'SHA256(domain17||header128), ECDSA Prehashed SHA256; rawr32||s32','payload_elf_sha256':hashlib.sha256(Path(payload_elf).read_bytes()).hexdigest(),'payload_bytes':len(payload),'policy_sha256':hashlib.sha256(policy).hexdigest(),'artifacts':records}
    (out/'fixtures.json').write_text(json.dumps(result,indent=2)+'\n');return result
