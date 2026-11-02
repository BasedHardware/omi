"""Bounded source characterization, not MCUboot emulation or hardware proof.

Retained overwrite-fast app-only path. Authentication is an oracle. Only power
cuts with readable healthy storage after reboot are modeled. No serial/BLE API.
"""
import ctypes
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

SDK = Path(os.environ.get('OMI_NCS_ROOT', '/opt/nordic/ncs/v2.9.0'))
LOADER = SDK / 'bootloader/mcuboot/boot/bootutil/src/loader.c'
PUBLIC = SDK / 'bootloader/mcuboot/boot/bootutil/src/bootutil_public.c'
MAX = (255, 255, 65535, 4294967295)
IMAGE_BYTES = 248516
MAGIC = 0x96f3b83d


def sha(data): return hashlib.sha256(data).hexdigest()


def comparator_library(directory):
    """Compile ONLY exact pure comparator from pinned loader as host C."""
    source = LOADER.read_text()
    if sha(source.encode()) != 'c7fd7916441262e0f5acba84c9d5b400dc38d812a8afeb9ad78956a0473b7fc9':
        raise ValueError('unsupported loader source: characterization is pinned')
    start = source.index('boot_version_cmp(const struct image_version *ver1,')
    end = source.index('\n}\n', start) + 3
    snippet = source[start:end]
    c = '#include <stdint.h>\nstruct image_version { uint8_t iv_major, iv_minor; uint16_t iv_revision; uint32_t iv_build_num; };\nint\n' + snippet
    output = Path(directory) / ('cmp.dylib' if sys.platform == 'darwin' else 'cmp.so')
    path = Path(directory) / 'cmp.c'
    path.write_text(c)
    shared = ['-dynamiclib'] if sys.platform == 'darwin' else ['-shared', '-fPIC']
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror'] + shared + [str(path), '-o', str(output)], check=True)
    class Version(ctypes.Structure):
        _fields_ = [('major', ctypes.c_uint8), ('minor', ctypes.c_uint8), ('revision', ctypes.c_uint16), ('build', ctypes.c_uint32)]
    library = ctypes.CDLL(str(output))
    library.boot_version_cmp.argtypes = [ctypes.POINTER(Version), ctypes.POINTER(Version)]
    library.boot_version_cmp.restype = ctypes.c_int
    def compare(a, b): return library.boot_version_cmp(ctypes.byref(Version(*a)), ctypes.byref(Version(*b)))
    return compare, {'loader_sha256': sha(source.encode()), 'comparator_sha256': sha(snippet.encode()), 'compiled': 'exact comparator only; build-number define absent'}


def pending(secondary_magic, secondary_ok):
    """Faithful two secondary-priority rows of boot_swap_tables, public.c:102.
    Initial primary copy_done UNSET; no overwrite path sets it. REVERT row is
    unreachable under this explicit admitted initial trailer assumption.
    """
    return secondary_magic == 'good' and secondary_ok in ('unset', 'set')


def reboot(compare, candidate, primary_version, *, primary_magic_erased=False,
           primary_valid=False, secondary_valid=True, secondary_eligible=True, secondary_magic='good', secondary_ok='unset'):
    # loader: boot_prepare_image_for_update -> boot_validated_swap_type ->
    # boot_validate_slot(SECONDARY) -> boot_copy_image -> validate PRIMARY.
    if not pending(secondary_magic, secondary_ok):
        return 'primary' if primary_valid else 'no_boot'
    if not secondary_eligible:
        return 'primary' if primary_valid else 'no_boot'  # erased/nonbootable header: no validation
    if compare(candidate, primary_version) < 0 and not primary_magic_erased:
        return 'primary_source_erased' if primary_valid else 'no_boot_source_erased'
    if not secondary_valid:
        return 'primary_source_erased' if primary_valid else 'no_boot_source_erased'
    return 'retry_copy'  # source retained through complete destination copy


def header(version):
    return struct.pack('<IIHHIIBBHI', MAGIC, 0, 512, 0, IMAGE_BYTES-848, 0, *version) + bytes(4)


def version_at(raw): return struct.unpack_from('<BBHI', raw, 20)


def snapshots(candidate, old):
    # Every header word boundary. Completed words follow actual ascending NVMC
    # writes; later bytes remain erased. Authentication becomes true only once
    # all signed bytes+TLV have copied. Body cuts collapse by identical predicates.
    target = header(candidate)
    yield 'request_not_pending', old, False, True, False, 'unset', 'unset'
    yield 'request_torn_magic', old, False, True, True, 'bad', 'unset'
    yield 'request_good_magic', old, False, True, True, 'good', 'unset'
    yield 'request_torn_image_ok', old, False, True, True, 'good', 'bad'
    yield 'request_confirmed', old, False, True, True, 'good', 'set'
    # Primary erase symbolic equivalence classes: damaged magic/version.
    # FF is maximal version; arbitrary partial erasure may produce intermediates.
    for magic_erased in (False, True):
        for ver in (old, candidate, MAX):
            yield 'erase_symbolic', ver, magic_erased, False, True, 'good', 'unset'
    for n in range(0, 33, 4):
        raw = target[:n] + b'\xff'*(32-n)
        yield 'header_word_%d' % n, version_at(raw), raw[:4] == b'\xff'*4, False, True, 'good', 'unset'
    # Partial version writes can leave any bitwise intermediate <=MAX. Include
    # exact source, erased endpoint, byte boundaries and all one-bit witnesses.
    for n in range(20, 29):
        raw = target[:n]+b'\xff'*(32-n)
        yield 'header_byte_class_%d' % n, version_at(raw), False, False, True, 'good', 'unset'
    for bit in range(64):
        raw = bytearray(b'\xff'*8)
        raw[bit//8] &= ~(1 << (bit%8))
        yield 'version_bit_class', struct.unpack('<BBHI', raw), False, False, True, 'good', 'unset'
    yield 'body_incomplete', candidate, False, False, True, 'good', 'unset'
    yield 'signed_copy_complete', candidate, False, True, True, 'good', 'unset'
    for magic in ('unset', 'bad', 'good'):
        for ok in ('unset', 'bad', 'set'):
            yield 'secondary_cleanup', candidate, False, True, False, magic, ok


def run():
    if sha(PUBLIC.read_bytes()) != '1bf0812387f8e980027d7437f6d02319a923a81e0e72f733ed26619802db9822':
        raise ValueError('unsupported trailer source: characterization is pinned')
    with tempfile.TemporaryDirectory(prefix='cv1-loader-host-') as directory:
        compare, provenance = comparator_library(directory)
        cases = {'conventional': ((0,0,0,0),(1,0,0,0)),
                 'equal_conventional': ((3,0,21,0),(3,0,21,1)),
                 'maximum_bootstrap': ((0,0,0,0),MAX),
                 'maximum_future_equal': (MAX,(255,255,65535,1)),
                 'maximum_to_lower_rejected_before_copy': (MAX,(4,0,0,0))}
        results = {}
        for name, (old, candidate) in cases.items():
            initial = reboot(compare, candidate, old, primary_valid=True)
            if initial != 'retry_copy':
                results[name] = {'initial': initial, 'copy_reachable': False, 'states': 1, 'failures': []}
                continue
            rows = []
            for phase, version, erased, pv, sv, sm, so in snapshots(candidate,old):
                outcome = reboot(compare,candidate,version,primary_magic_erased=erased,
                                 primary_valid=pv,secondary_valid=sv,secondary_magic=sm,secondary_ok=so)
                rows.append({'phase':phase,'primary_version':version,'outcome':outcome})
            results[name] = {'initial':initial, 'copy_reachable':True,'states':len(rows),
                             'failures':[x for x in rows if x['outcome'].startswith('no_boot')],
                             'state_digest':sha(json.dumps(rows,sort_keys=True).encode()),
                             'phase_classes':sorted(set(x['phase'] for x in rows))}
        return {'schema':1,'kind':'source characterization; NOT whole loader execution',
                'provenance': dict(provenance, public_sha256=sha(PUBLIC.read_bytes())),
                'config':{'overwrite_fast':True,'primary_validation':True,'downgrade_prevention':True,
                          'compare_build_number':False,'hardware_counter':False,'bootstrap':False},
                'image_bytes':IMAGE_BYTES,'copy_padding_bytes':4,'body_word_cutpoints_collapsed':(IMAGE_BYTES-32)//4,
                'cases':results,
                'symbolic_argument':'For maximum candidate, no unsigned major/minor/revision can exceed candidate. Arbitrary torn primary header therefore cannot trigger secondary downgrade erasure. Source remains intact until destination signed bytes complete; cleanup has valid destination. Repeated cuts reenter these same phases.',
                'limits':['No functional supervisor/startup/recovery proof','No cryptographic signature execution; valid signed source assumed',
                          'No analog torn-flash/correlated corruption or permanent I/O failure model',
                          'Initial stable trailer copy_done UNSET required; unknown shipped cohorts not admitted',
                          'Maximum versions sacrifice root semantic antirollback: equal versions accepted; build ignored',
                          'No alternate functional fallback after old image overwrite; broken signed supervisor remains fatal',
                          'No signed maximum-version artifact created or adopted']}

if __name__ == '__main__':
    print(json.dumps(run(),indent=2))
