#!/usr/bin/env python3
"""Check bound coalescing evidence; missing production gates must fail closed.

This checks evidence integrity/completeness, not release authority. Lead2 GO
and the Release: Omi prod owner remain mandatory even for a complete packet.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

GATES = (
    'matched_billed_reads_per_admitted_audio_hour',
    'flat_notes_transcript_speaker_quality',
    'serving_image_source_binding',
    'actual_latency_and_stale_budget',
    'mixed_reader_rollback',
    'user_open_client_signal',
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(packet, root, repository, *, qualification):
    errors = []
    source = packet['source']
    if not re.fullmatch('[0-9a-f]{40}', source['sha']):
        errors.append('invalid source sha')
    current = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip()
    if source['sha'] != current:
        errors.append('candidate source HEAD differs from packet')
    for path, expected in source['files_sha256'].items():
        relative = Path(path)
        if relative.is_absolute() or '..' in relative.parts or sha(repository / relative) != expected:
            errors.append('candidate source hash mismatch: ' + path)
    for name, expected in packet['artifacts_sha256'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or sha(root / relative) != expected:
            errors.append('evidence hash mismatch: ' + name)
    tests = ET.parse(root / packet['rehearsal']['junit']).getroot()
    cases = list(tests.iter('testcase'))
    if not cases or any(list(case.iter('failure')) or list(case.iter('error')) for case in cases):
        errors.append('rehearsal test failures or missing cases')
    observed = []
    for case in cases:
        properties = {p.attrib['name']: p.attrib['value'] for p in case.iter('property')}
        if properties.get('sample_conservation') == 'PASS':
            observed.append(properties)
    if sorted(int(p['created_units']) for p in observed) != [1, 2]:
        errors.append('missing paired grouped/OFF admission evidence')
    if any(int(p['source_frames']) != 32000 or int(p['original_uploads']) != 2 for p in observed):
        errors.append('source admission workload mismatch')
    corpus = packet['original_workload']
    if any(
        json.loads(p['original_raw_sha256']) != [upload['raw_sha256'] for upload in corpus['uploads']] for p in observed
    ):
        errors.append('immutable raw input manifest differs from rehearsal')
    if corpus['source_frames'] != 32000 or corpus['sample_rate_hz'] != 16000 or len(corpus['uploads']) != 2:
        errors.append('invalid original source manifest')
    if corpus['denominator'] != 'original canonical source samples counted once before grouping':
        errors.append('incorrect audio denominator')
    if packet['booked_savings_dollars_per_day'] != 0:
        errors.append('unqualified packet must book zero savings')
    if 'scan_repair' in packet:
        scans = [
            {p.attrib['name']: p.attrib['value'] for p in case.iter('property')}
            for case in cases
            if 'test_35_contenders_one_scanner_and_fixed_operation_budget' in case.attrib.get('name', '')
        ]
        if len(scans) != 1:
            errors.append('missing strict scan contention rehearsal')
        else:
            scan = scans[0]
            operations = json.loads(scan.get('steady_attempt_operations', '{}'))
            expected = {'query': 1, 'read_coalesce_quota': 2, 'read_leases': 37, 'attempt_write_coalesce_quota': 1}
            if any(operations.get(key) != value for key, value in expected.items()):
                errors.append('strict scan operation budget differs from rehearsal')
            if scan.get('contenders') != '35' or scan.get('takeover_and_stale_writer_fencing') != 'PASS':
                errors.append('missing strict scan contender/takeover evidence')
        if qualification and packet['scan_repair'].get('production_scan_health') != 'PASS':
            errors.append('NOT_QUALIFIED: stable strict-scan production readback')
    if qualification:
        errors += ['NOT_QUALIFIED: ' + name for name in GATES if packet['gates'].get(name) != 'PASS']
        if packet['rehearsal']['kind'] != 'staging_end_to_end':
            errors.append('local admission emulator is not end-to-end staging savings proof')
        if any(value == 'UNKNOWN' for value in packet['effective_runtime_flags'].values()):
            errors.append('effective runtime flags are unknown')
        # Observational baseline + a synthetic created-unit count cannot be
        # relabeled as billed reads or persisted units by optimistic gate flags.
        measured = packet.get('matched_workload_measurement')
        if not measured:
            errors.append('matched-workload billed-read receipt is missing')
        else:
            before, after = measured['before'], measured['after']
            if before['input_manifest_sha256'] != after['input_manifest_sha256']:
                errors.append('before/after source workload differs')
            if before['admitted_source_frames'] != after['admitted_source_frames']:
                errors.append('before/after admitted source denominator differs')
            for window in (before, after):
                if not window['queries'] or window['true_persisted_units'] <= 0 or window['download_observations'] <= 0:
                    errors.append('incomplete measured counters/queries')
                if sum(window['read_components'].values()) != window['billed_batch_reads']:
                    errors.append('billed-read numerator coverage mismatch')
            if after['billed_batch_reads'] >= before['billed_batch_reads']:
                errors.append('no measured read reduction on identical admitted source workload')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        '--evidence-only', action='store_true', help='verify local evidence without granting qualification'
    )
    args = parser.parse_args()
    try:
        packet = json.loads(args.packet.read_text())
        errors = check(packet, args.packet.parent, args.repository, qualification=not args.evidence_only)
        if errors:
            print('FAIL\n' + '\n'.join(errors))
            return 1
        print('PASS: evidence integrity only; no release/activation authority')
        return 0
    except (KeyError, TypeError, ValueError, OSError, ET.ParseError, subprocess.CalledProcessError) as error:
        print('FAIL: ' + str(error))
        return 1


if __name__ == '__main__':
    sys.exit(main())
