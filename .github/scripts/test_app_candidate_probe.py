import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

SPEC = importlib.util.spec_from_file_location('probe', Path(__file__).with_name('app_candidate_probe.py'))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.args = SimpleNamespace(revision='candidate', image='gcr.io/proj/app@sha256:' + 'a' * 64)
        self.runtime = 'gcr.io/proj/app@sha256:' + 'b' * 64
        self.baseline = {'status': {'traffic': [{'revisionName': 'rollback', 'percent': 100}]}}
        self.service = copy.deepcopy(self.baseline)
        self.service['status']['traffic'].append({'revisionName': 'candidate', 'tag': 'candidate-url'})
        self.revision = {'metadata': {'name': 'candidate'},
                         'status': {'imageDigest': self.runtime, 'conditions': [{'type': 'Ready', 'status': 'True'}]},
                         'spec': {'containers': [{'image': self.args.image}]}}

    def test_zero_traffic_candidate_and_json_receipt_roundtrip(self):
        probe.check_state(self.service, self.revision, self.args, self.baseline, self.runtime)
        traffic = probe.traffic(self.baseline)
        self.assertEqual(traffic, json.loads(json.dumps(traffic)))

    def test_candidate_traffic_and_changed_baseline_refuse(self):
        for rows in [[{'revisionName': 'candidate', 'percent': 100}],
                     [{'revisionName': 'rollback', 'percent': 99}, {'revisionName': 'candidate', 'percent': 1}],
                     [{'revisionName': 'foreign', 'percent': 100}], []]:
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                probe.check_state({'status': {'traffic': rows}}, self.revision, self.args, self.baseline, self.runtime)

    def test_wrong_revision_digest_mutable_image_and_readiness_refuse(self):
        for mutation in [lambda r: r['metadata'].update(name='foreign'),
                         lambda r: r['status'].update(imageDigest='wrong'),
                         lambda r: r['spec']['containers'][0].update(image='mutable:tag'),
                         lambda r: r['status'].update(conditions=[])]:
            r = copy.deepcopy(self.revision)
            mutation(r)
            with self.assertRaises(RuntimeError):
                probe.check_state(self.service, r, self.args, self.baseline, self.runtime)

    def test_final_recheck_resolves_registry_and_binds_both_digests_and_receipt(self):
        manifest = index_manifest()
        lineage = probe.resolve_lineage(self.args.image, manifest)
        identity = {'revision': 'candidate', 'image': self.args.image, 'runtime_image': self.runtime,
                    'source': '1' * 40, 'carrier': '2' * 40, 'service': 'app', 'project': 'proj',
                    'region': 'us-central1'}
        receipt = {'identity': identity, 'lineage': lineage, 'result': 'PASS',
                   'baseline': probe.traffic(self.baseline)}
        with tempfile.TemporaryDirectory() as directory:
            baseline_path, receipt_path = Path(directory) / 'baseline.json', Path(directory) / 'receipt.json'
            baseline_path.write_text(json.dumps(self.baseline))
            argv = ['probe', 'recheck', '--baseline', str(baseline_path), '--receipt', str(receipt_path)]
            for key in ['revision', 'image', 'source', 'carrier', 'service', 'project', 'region']:
                argv.extend(['--' + key, identity[key]])
            wrong_receipt = copy.deepcopy(receipt)
            wrong_receipt['lineage']['runtime_image']['digest'] = 'sha256:' + 'd' * 64
            changed_runtime = copy.deepcopy(self.revision)
            changed_runtime['status']['imageDigest'] = 'gcr.io/proj/app@sha256:' + 'd' * 64
            changed_index = copy.deepcopy(manifest)
            changed_index['manifests'][0]['digest'] = 'sha256:' + 'd' * 64
            wrong_build = copy.deepcopy(self.revision)
            wrong_build['spec']['containers'][0]['image'] = 'gcr.io/proj/app@sha256:' + 'd' * 64
            normalized = copy.deepcopy(self.revision)
            normalized['spec']['containers'][0]['image'] = self.runtime
            for name, revision, document, registry, succeeds in [
                ('index differs from child', self.revision, receipt, manifest, True),
                ('Cloud Run normalizes spec to verified child', normalized, receipt, manifest, True),
                ('runtime changed', changed_runtime, receipt, manifest, False),
                ('registry lineage changed', changed_runtime, receipt, changed_index, False),
                ('receipt lineage changed', self.revision, wrong_receipt, manifest, False),
                ('build pin changed', wrong_build, receipt, manifest, False),
            ]:
                with self.subTest(name=name):
                    receipt_path.write_text(json.dumps(document))
                    with patch.object(sys, 'argv', argv), patch.object(probe, 'run', return_value=json.dumps(registry)) as read:
                        with patch.object(probe, 'cloud', side_effect=lambda kind, *_: self.service if kind == 'services' else revision):
                            if succeeds:
                                probe.main()
                            else:
                                with self.assertRaises(RuntimeError):
                                    probe.main()
                        read.assert_called_once_with('docker', 'buildx', 'imagetools', 'inspect', '--raw', self.args.image)

    def test_image_platform_and_both_source_identities(self):
        image = {'Os': 'linux', 'Architecture': 'amd64', 'Config': {'Labels': {
            'org.opencontainers.image.revision': 'product', 'me.omi.carrier-source': 'carrier'}}}
        probe.check_image(image, 'product', 'carrier')
        for key, value in [('Os', 'darwin'), ('Architecture', 'arm64')]:
            wrong = copy.deepcopy(image)
            wrong[key] = value
            with self.assertRaises(RuntimeError):
                probe.check_image(wrong, 'product', 'carrier')
        for source, carrier in [('wrong', 'carrier'), ('product', 'wrong')]:
            with self.assertRaises(RuntimeError):
                probe.check_image(image, source, carrier)

    def test_candidate_redirect_or_missing_framing_refuse(self):
        headers = {'x-frame-options': 'SAMEORIGIN', 'content-security-policy': "frame-ancestors 'self'",
                   'cache-control': 'no-store'}
        probe.framed(200, headers, b'helper', True)
        for status, body, h in [(302, b'helper', headers), (200, b'', headers), (200, b'helper', {}),
                                (200, b'helper', {**headers, 'cache-control': 'public'})]:
            with self.assertRaises(RuntimeError):
                probe.framed(status, h, body, True)
        for url in ['http://candidate.a.run.app', 'https://app.omi.me', 'https://x.a.run.app/path']:
            with self.assertRaises(RuntimeError):
                probe.candidate_gets(url)


def index_manifest():
    return {'schemaVersion': 2, 'mediaType': 'application/vnd.oci.image.index.v1+json', 'manifests': [
        {'mediaType': 'application/vnd.oci.image.manifest.v1+json', 'digest': 'sha256:' + 'b' * 64,
         'platform': {'os': 'linux', 'architecture': 'amd64'}},
        {'mediaType': 'application/vnd.oci.image.manifest.v1+json', 'digest': 'sha256:' + 'c' * 64,
         'platform': {'os': 'unknown', 'architecture': 'unknown'},
         'annotations': {'vnd.docker.reference.type': 'attestation-manifest'}},
    ]}


class LineageTests(unittest.TestCase):
    def setUp(self):
        self.build = 'gcr.io/proj/app@sha256:' + 'a' * 64

    def test_index_runtime_child_is_distinct_and_attestations_are_excluded(self):
        manifest = index_manifest()
        # Even an attestation claiming the runtime platform is never runnable.
        manifest['manifests'][1]['platform'] = {'os': 'linux', 'architecture': 'amd64'}
        evidence = probe.resolve_lineage(self.build, manifest)
        self.assertEqual(evidence['build_image']['reference'], self.build)
        self.assertEqual(evidence['runtime_image']['reference'], 'gcr.io/proj/app@sha256:' + 'b' * 64)
        self.assertNotEqual(evidence['build_image']['digest'], evidence['runtime_image']['digest'])

    def test_direct_image_manifest_keeps_one_digest(self):
        evidence = probe.resolve_lineage(self.build, {'schemaVersion': 2,
            'mediaType': 'application/vnd.oci.image.manifest.v1+json'})
        self.assertEqual(evidence['runtime_image']['reference'], self.build)

    def test_absent_ambiguous_or_invalid_child_fails_closed(self):
        original = index_manifest()
        bad_digest = copy.deepcopy(original['manifests'][0]); bad_digest['digest'] = 'not-a-digest'
        bad_media = copy.deepcopy(original['manifests'][0]); bad_media['mediaType'] = 'unknown'
        wrong_platform = copy.deepcopy(original['manifests'][0]); wrong_platform['platform']['architecture'] = 'arm64'
        for descriptors in [None, [], original['manifests'][1:], [wrong_platform], [bad_digest], [bad_media],
                            [original['manifests'][0], original['manifests'][0]]]:
            with self.subTest(descriptors=descriptors), self.assertRaises(RuntimeError):
                probe.resolve_lineage(self.build, {**original, 'manifests': descriptors})


class WorkflowBoundaryTests(unittest.TestCase):
    def test_probe_precedes_promotion_and_recheck_precedes_traffic(self):
        root = Path(__file__).resolve().parents[2]
        action = yaml.safe_load((root / '.github/actions/deploy-public-build/action.yml').read_text())
        steps = action['runs']['steps']
        names = [s['name'] for s in steps if 'name' in s]
        self.assertLess(names.index('Save app rollback traffic baseline'), names.index('Deploy candidate revision'))
        self.assertLess(names.index('Deploy candidate revision'), names.index('Verify exact Linux app candidate before promotion'))
        self.assertLess(names.index('Verify exact Linux app candidate before promotion'), names.index('Promote browser-accepted candidate'))
        deploy = next(s for s in steps if s.get('name') == 'Deploy candidate revision')
        self.assertIn('steps.app-image.outputs.reference', deploy['with']['image'])
        gate = next(s for s in steps if s.get('name') == 'Verify exact Linux app candidate before promotion')
        self.assertNotIn('continue-on-error', gate)
        promotion = yaml.safe_load((root / '.github/actions/public-build-candidate-promotion/action.yml').read_text())
        code = next(s['run'] for s in promotion['runs']['steps'] if s.get('name') == 'Promote browser-accepted candidate')
        self.assertLess(code.index('app_candidate_probe.py recheck'), code.index('gcloud run services update-traffic'))
        self.assertIn('set -euo pipefail', code)


if __name__ == '__main__':
    unittest.main()
