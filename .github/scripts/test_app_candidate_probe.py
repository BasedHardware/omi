import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import yaml

SPEC = importlib.util.spec_from_file_location('probe', Path(__file__).with_name('app_candidate_probe.py'))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.args = SimpleNamespace(revision='candidate', image='gcr.io/proj/app@sha256:' + 'a' * 64)
        self.baseline = {'status': {'traffic': [{'revisionName': 'rollback', 'percent': 100}]}}
        self.service = copy.deepcopy(self.baseline)
        self.service['status']['traffic'].append({'revisionName': 'candidate', 'tag': 'candidate-url'})
        self.revision = {'metadata': {'name': 'candidate'},
                         'status': {'imageDigest': self.args.image, 'conditions': [{'type': 'Ready', 'status': 'True'}]},
                         'spec': {'containers': [{'image': self.args.image}]}}

    def test_zero_traffic_candidate_and_json_receipt_roundtrip(self):
        probe.check_state(self.service, self.revision, self.args, self.baseline)
        traffic = probe.traffic(self.baseline)
        self.assertEqual(traffic, json.loads(json.dumps(traffic)))

    def test_candidate_traffic_and_changed_baseline_refuse(self):
        for rows in [[{'revisionName': 'candidate', 'percent': 100}],
                     [{'revisionName': 'rollback', 'percent': 99}, {'revisionName': 'candidate', 'percent': 1}],
                     [{'revisionName': 'foreign', 'percent': 100}], []]:
            with self.subTest(rows=rows), self.assertRaises(RuntimeError):
                probe.check_state({'status': {'traffic': rows}}, self.revision, self.args, self.baseline)

    def test_wrong_revision_digest_mutable_image_and_readiness_refuse(self):
        for mutation in [lambda r: r['metadata'].update(name='foreign'),
                         lambda r: r['status'].update(imageDigest='wrong'),
                         lambda r: r['spec']['containers'][0].update(image='mutable:tag'),
                         lambda r: r['status'].update(conditions=[])]:
            r = copy.deepcopy(self.revision)
            mutation(r)
            with self.assertRaises(RuntimeError):
                probe.check_state(self.service, r, self.args, self.baseline)

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
