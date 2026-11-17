"""Verify honest access evidence, bounded hints and actual publication outcomes offline."""

import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
import copy
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import registry_access as access
import publish_operator as publisher
import test_publication_controls as controls
from test_operator_ingress import inputs


class AccessTests(unittest.TestCase):
    def test_reviewed_allow_and_trust_is_not_effective_permission_claim(self):
        c, _, _ = controls.ControlTests().prepared()
        access.validate_evidence(c)
        self.assertIsNone(c['registry_write_authorization'])
        self.assertEqual(
            c['registry_access_evidence']['effective_authorization'], 'UNKNOWN_UNTIL_ACTUAL_REGISTRY_OPERATIONS'
        )

    def test_wrong_principal_resource_decision_or_receipt_refused(self):
        for key, value in (
            ('principal', 'other'),
            ('repository', 'other'),
            ('iam_resource', 'other'),
            ('decision', 'other'),
            ('effective_authorization', 'VERIFIED'),
            ('allow_policy_receipt_sha256', ''),
            ('wif_metadata_receipt_sha256', ''),
            ('sa_trust_receipt_sha256', ''),
        ):
            c, _, _ = controls.ControlTests().prepared()
            c['registry_access_evidence'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                access.validate_evidence(c)

    def test_non_string_receipt_digests_use_deliberate_refusal(self):
        for key in ('allow_policy_receipt_sha256', 'wif_metadata_receipt_sha256', 'sa_trust_receipt_sha256'):
            for value in (None, False, 0, [], {}):
                c, _, _ = controls.ControlTests().prepared()
                c['registry_access_evidence'][key] = value
                with self.subTest(key=key, value=value), self.assertRaisesRegex(
                    ValueError, '^REVIEWED_EXISTING_ALLOW_AND_TRUST_FOR_BOUNDED_ATTEMPT_REQUIRED$'
                ):
                    access.validate_evidence(c)

    def test_legacy_affirmative_assertion_and_closed_contract_refused(self):
        for key, value in (
            ('registry_write_authorization', {'existing_authorization_verified': True}),
            ('status', 'SOURCE_ONLY_NOT_APPROVED'),
        ):
            c, _, _ = controls.ControlTests().prepared()
            c[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                access.validate_evidence(c)

    def hint(self, body, error=None):
        opener = unittest.mock.Mock()
        if error:
            opener.open.side_effect = error
        else:
            opener.open.return_value.__enter__ = unittest.mock.Mock(return_value=io.BytesIO(body))
            opener.open.return_value.__exit__ = unittest.mock.Mock(return_value=False)
        with patch.object(access, 'build_opener', return_value=opener):
            result = access.permission_hint('sensitive-fixture-token')
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, access.URL)
        self.assertEqual(request.get_method(), 'POST')
        self.assertNotIn('sensitive-fixture-token', request.full_url)
        self.assertEqual(json.loads(request.data), {'permissions': list(access.PERMISSIONS)})
        self.assertFalse(result['authorization_proof'])
        self.assertNotIn('sensitive-fixture-token', json.dumps(result))
        return result

    def test_complete_hint_is_diagnostic_not_authorization(self):
        self.hint(json.dumps({'permissions': list(access.PERMISSIONS)}).encode())

    def test_missing_malformed_or_oversized_hints_refused(self):
        for body in (
            b'{}',
            b'not json',
            b'[]',
            b'x' * 65537,
            json.dumps({'permissions': list(access.PERMISSIONS[:-1])}).encode(),
            json.dumps({'permissions': [True]}).encode(),
        ):
            with self.subTest(body=body[:30]), self.assertRaises(ValueError):
                self.hint(body)

    def test_network_and_auth_errors_do_not_log_response_or_token(self):
        for error in (
            URLError('sensitive-fixture-token'),
            HTTPError(access.URL, 403, 'sensitive-fixture-token', {}, io.BytesIO(b'secret-body')),
        ):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(ValueError) as caught:
                    self.hint(b'', error)
                self.assertEqual(str(caught.exception), 'REGISTRY_PERMISSION_HINT_UNAVAILABLE')

    def test_redirect_never_forwards_authorization(self):
        handler = access.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, 'redirect', {}, 'https://other.invalid'))


class PublicationOutcomeTests(unittest.TestCase):
    def run_case(self, mode, expected_error=None):
        c, _, receipt = controls.ControlTests().prepared()
        _, release, parts = inputs()
        raw = b'{"reviewed":"manifest"}'
        digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
        c['oci_manifest_digest'] = digest
        receipt['oci_manifest_digest'] = digest
        checked = {'manifest_digest': digest, 'config_digest': 'sha256:' + 'a' * 64, 'layers': []}
        commands = []
        auth_paths = []

        def command(argv, env=None):
            commands.append(argv)
            if argv == ['skopeo', '--version']:
                return b'skopeo version 1.13.3'
            if argv == ['gcloud', 'auth', 'print-access-token']:
                return b'sensitive-fixture-token'
            if argv[:2] == ['skopeo', 'copy']:
                self.assertNotIn('sensitive-fixture-token', ' '.join(argv))
                flag = '--dest-authfile' if '--dest-authfile' in argv else '--src-authfile'
                auth_path = Path(argv[argv.index(flag) + 1])
                self.assertEqual(auth_path.stat().st_mode & 0o777, 0o600)
                auth_paths.append(auth_path)
                if '--dest-authfile' in argv and mode == 'push-fails':
                    raise RuntimeError('REGISTRY_COMMAND_FAILED')
                return b''
            self.fail(argv)

        def hint(token):
            self.assertEqual(token, 'sensitive-fixture-token')
            if mode == 'hint-fails':
                raise ValueError('REGISTRY_PERMISSION_HINT_INCOMPLETE_NO_WRITE_ATTEMPT')
            return {'authorization_proof': False, 'result': 'CALLER_PERMISSION_HINT_COMPLETE'}

        before = subprocess.CompletedProcess([], 1, stdout=b'', stderr=b'manifest unknown')
        if mode == 'existing':
            before = subprocess.CompletedProcess([], 0, stdout=raw, stderr=b'')
        elif mode == 'conflicting-existing':
            before = subprocess.CompletedProcess([], 0, stdout=b'{"different":"manifest"}', stderr=b'')
        elif mode == 'unknown-destination':
            before = subprocess.CompletedProcess([], 1, stdout=b'', stderr=b'permission denied')

        def inspect_command(argv, **_kwargs):
            self.assertEqual(argv[:3], ['skopeo', 'inspect', '--raw'])
            auth_path = Path(argv[argv.index('--authfile') + 1])
            self.assertEqual(auth_path.stat().st_mode & 0o777, 0o600)
            auth_paths.append(auth_path)
            return before

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'input'
            directory.mkdir()
            (directory / 'operator.oci.tar').write_bytes(b''.join(parts))
            output = root / 'publication.json'
            with patch.object(publisher, 'release_metadata', return_value=release), patch.object(
                publisher, 'validate', return_value=checked
            ), patch.object(publisher, 'command', side_effect=command), patch.object(
                publisher, 'permission_hint', side_effect=hint
            ), patch.object(
                publisher.subprocess, 'run', side_effect=inspect_command
            ) as inspect, patch.dict(
                os.environ, {'GITHUB_WORKFLOW_SHA': 'w', 'GITHUB_RUN_ID': '1'}
            ):
                if expected_error:
                    with self.assertRaisesRegex(ValueError, '^' + expected_error + '$'):
                        publisher.publish(c, directory, receipt, output)
                elif mode in ('push-fails', 'hint-fails'):
                    with self.assertRaises((ValueError, RuntimeError)):
                        publisher.publish(c, directory, receipt, output)
                else:
                    publisher.publish(c, directory, receipt, output)
                result = json.loads(output.read_text())
                self.assertNotIn('sensitive-fixture-token', output.read_text())
                self.assertTrue(all(not path.exists() for path in auth_paths))
                if mode == 'hint-fails':
                    inspect.assert_not_called()
            return result, commands

    def test_hint_failure_prevents_every_registry_operation(self):
        result, commands = self.run_case('hint-fails')
        self.assertFalse(result['write_attempted'])
        self.assertFalse(any(c[:2] == ['skopeo', 'copy'] for c in commands))

    def test_conflicting_existing_digest_prevents_copy_and_cleans_auth(self):
        result, commands = self.run_case('conflicting-existing', 'CONFLICTING_EXISTING_PUBLICATION')
        self.assertFalse(result['write_attempted'])
        self.assertFalse(any(c[:2] == ['skopeo', 'copy'] for c in commands))

    def test_unknown_destination_prevents_copy_and_cleans_auth(self):
        result, commands = self.run_case('unknown-destination', 'DESTINATION_STATE_UNKNOWN')
        self.assertFalse(result['write_attempted'])
        self.assertFalse(any(c[:2] == ['skopeo', 'copy'] for c in commands))

    def test_partial_push_is_unknown_until_successful_readback(self):
        result, _ = self.run_case('push-fails')
        self.assertEqual(result['publication_state'], 'PUBLICATION_ATTEMPTED_OUTCOME_UNKNOWN_UNTIL_READBACK')
        self.assertEqual(result['effective_registry_write'], 'UNVERIFIED')

    def test_existing_artifact_readback_never_claims_write_authorization(self):
        result, commands = self.run_case('existing')
        self.assertFalse(result['write_attempted'])
        self.assertEqual(result['effective_registry_write'], 'NOT_TESTED_EXISTING_EXACT_ARTIFACT_REUSED')
        self.assertFalse(any('--dest-authfile' in c for c in commands))

    def test_successful_write_and_full_readback_are_separate_operation_evidence(self):
        result, _ = self.run_case('success')
        self.assertTrue(result['write_attempted'])
        self.assertEqual(result['effective_registry_write'], 'CONFIRMED_BY_SUCCESSFUL_COPY_AND_READBACK')
        self.assertFalse(result['registry_permission_hint']['authorization_proof'])
        self.assertFalse(result['deployed'])
        self.assertEqual(result['runtime_admission'], 'CLOSED')


if __name__ == '__main__':
    unittest.main()
