"""Keep full-copy catalog source, nested programs and qualification proof bound offline."""

import ast, copy, hashlib, importlib.util, json, os, pathlib, sys, tempfile, types, unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(1, str(ROOT))
import qualification_profile as P
import image_smoke, preflight, qualify_operator, publish_operator

C = json.loads((pathlib.Path(qualify_operator.__file__).parent / 'artifact-contract.json').read_text())


def refusal():
    return {
        'result': 'GENERAL_COPY_SOURCE_CHECKS_REACHED_CREDENTIAL_REFUSAL',
        'catalog_sha256': P.CATALOG_SHA,
        'uid': 1000,
        'full_working_blob_check': True,
        'ignored_file_check': True,
        'credential_refusal_injected': True,
        'real_credentials_used': False,
        'sql_called': False,
        'elapsed_ms': 100,
    }


def suite():
    return {
        'result': 'GENERAL_COPY_FIXED_SUITE_PASS',
        'profile': P.PROFILE,
        'suite_sha256': P.SUITE_SHA,
        'test_ids_sha256': P.TEST_IDS_SHA,
        'tests_run': P.TESTS_EXPECTED,
        'tests_skipped': 0,
        'failures': 0,
        'errors': 0,
    }


def receipt():
    r = {
        key: C[key]
        for key in (
            'source_sha',
            'source_tree',
            'archive_sha256',
            'oci_manifest_digest',
            'build_inputs_sha256',
            'supervisor_sha256',
        )
    }
    r.update(
        result='NATIVE_AMD64_QUALIFIED_OFFLINE_ONLY',
        tests_run=P.TESTS_EXPECTED,
        tests_skipped=0,
        artifact_profile=P.PROFILE,
        catalog_profile=P.CATALOG_PROFILE,
        suite_sha256=P.SUITE_SHA,
        test_ids_sha256=P.TEST_IDS_SHA,
        uid=1000,
        container_network='none',
        real_state_accessed=False,
        production_calls=False,
        workflow_sha='w',
        run_id='1',
        resource_bound_source_refusal=refusal(),
        native_host={'system': 'Linux', 'machine': 'x86_64', 'docker_architecture': 'x86_64'},
        general_cli_import_smoke={
            'result': 'GENERAL_COPIER_CLI_IMPORT_PASS',
            'help_sha256': 'a' * 64,
            'git_sha256': 'b' * 64,
            'python_sha256': 'c' * 64,
            'git_path': '/usr/bin/git',
            'python_resolved': '/opt/python',
        },
    )
    return r


class GeneralProfileTests(unittest.TestCase):
    def test_exact_profile_required_not_old_readiness(self):
        P.validate_contract(C)
        for key in (
            'artifact_profile',
            'catalog_profile',
            'source_sha',
            'source_tree',
            'catalog_sha256',
            'catalog_contract_sha256',
            'catalog_structure_sha256',
            'suite_sha256',
            'test_ids_sha256',
            'tests_expected',
            'guard_sha256',
        ):
            c = copy.deepcopy(C)
            c[key] = 58 if key == 'tests_expected' else None
            with self.subTest(key=key), self.assertRaises(ValueError):
                P.validate_contract(c)

    def test_immutable_suite_count_ids_types_zero_skips(self):
        P.validate_suite(suite())
        for key, value in (
            ('tests_run', 58),
            ('tests_run', True),
            ('tests_skipped', 1),
            ('tests_skipped', False),
            ('test_ids_sha256', '0' * 64),
            ('suite_sha256', '0' * 64),
            ('errors', 1),
            ('failures', 1),
        ):
            r = suite()
            r[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                P.validate_suite(r)
        r = suite()
        r['extra'] = True
        with self.assertRaises(ValueError):
            P.validate_suite(r)

    def test_new_source_refusal_is_full_working_tree_and_bounded(self):
        image_smoke.validate_source_refusal(refusal(), P.CATALOG_SHA)
        for key, value in (
            ('full_working_blob_check', False),
            ('ignored_file_check', False),
            ('sql_called', True),
            ('elapsed_ms', 40000),
            ('elapsed_ms', True),
            ('catalog_sha256', '0' * 64),
            ('result', 'SOURCE_CHECKS_REACHED_CREDENTIAL_REFUSAL'),
        ):
            r = refusal()
            r[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                image_smoke.validate_source_refusal(r, P.CATALOG_SHA)
        with self.assertRaises(ValueError):
            image_smoke.source_refusal_program(P.READINESS_SHA)

    def test_pending_contract_cannot_preflight_or_touch_registry(self):
        with patch.object(preflight, 'validate_evidence', side_effect=AssertionError('registry called')):
            with self.assertRaisesRegex(ValueError, 'REVIEWED_SOURCE_CONTRACT_REQUIRED'):
                preflight.check(
                    C, {'REQUESTED_SOURCE': P.SOURCE, 'SKIP_PROOF': 'false', 'BREAK_GLASS_LOCK': 'false'}, 10**15
                )

    def test_publisher_rejects_old_count_source_profile_run_and_cli(self):
        with patch.dict(os.environ, {'GITHUB_WORKFLOW_SHA': 'w', 'GITHUB_RUN_ID': '1'}), patch.object(
            publish_operator, 'validate_evidence'
        ):
            publish_operator.validate_qualification(C, receipt())
            for key, value in (
                ('tests_run', 58),
                ('tests_skipped', False),
                ('artifact_profile', 'legacy'),
                ('run_id', '2'),
                ('source_sha', '0' * 40),
                ('suite_sha256', '0' * 64),
                ('uid', True),
            ):
                r = receipt()
                r[key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    publish_operator.validate_qualification(C, r)
            r = receipt()
            r['general_cli_import_smoke'] = {}
            with self.assertRaisesRegex(ValueError, 'ACTUAL_CLI_IMPORT'):
                publish_operator.validate_qualification(C, r)

    def test_fixed_actual_general_cli_in_smoke_and_programs_compile(self):
        self.assertIn("'database.jobstore','reconcile-page','--help'", image_smoke.PROGRAM)
        self.assertIn("'-E','-s','-B','-m'", image_smoke.PROGRAM)
        compile(image_smoke.PROGRAM, 'image-smoke', 'exec')
        compile(image_smoke.source_refusal_program(P.CATALOG_SHA), 'source-refusal', 'exec')

    def test_catalog_import_and_nested_source_refusal_child_compile(self):
        contract_spec = importlib.util.spec_from_file_location(
            'isolated_catalog_contract', ROOT / 'general_copy_catalog_contract.py'
        )
        contract = importlib.util.module_from_spec(contract_spec)
        contract_spec.loader.exec_module(contract)
        modules = {'general_copy_catalog_contract': contract}
        # The production image is Linux. Keep this import check portable without
        # replacing SDK modules or running any runtime/identity operation.
        if importlib.util.find_spec('pwd') is None:
            modules['pwd'] = types.ModuleType('pwd')
        catalog_spec = importlib.util.spec_from_file_location('isolated_catalog', ROOT / 'general_copy_catalog.py')
        catalog = importlib.util.module_from_spec(catalog_spec)
        with patch.dict(sys.modules, modules), patch.object(sys, 'path', list(sys.path)):
            catalog_spec.loader.exec_module(catalog)
        self.assertEqual(catalog.C.SOURCE, P.SOURCE)
        self.assertEqual(catalog.C.TREE, P.TREE)
        program = ast.parse(image_smoke.source_refusal_program(P.CATALOG_SHA))
        child = next(
            node.value
            for node in program.body
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'child' for t in node.targets)
        )
        compile(ast.literal_eval(child), 'source-refusal-child', 'exec')

    def test_complete_source_vector_matches_all_nine_migrations(self):
        spec = importlib.util.spec_from_file_location(
            'isolated_source_vector', ROOT / 'general_copy_catalog_contract.py'
        )
        contract = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contract)
        self.assertEqual([row[0] for row in contract.SOURCE_VECTOR], list(range(1, 10)))
        migrations = ROOT.parents[1] / 'database/jobstore/migrations'
        for version, name, expected in contract.SOURCE_VECTOR:
            with self.subTest(version=version):
                self.assertEqual(
                    hashlib.sha256((migrations / f'{version:04d}_{name}.sql').read_bytes()).hexdigest(), expected
                )

    def test_missing_actual_cli_report_has_named_refusal(self):
        report = receipt()['general_cli_import_smoke']
        self.assertEqual(qualify_operator.cli_import_report(json.dumps(report)), report)
        for output in ('', 'unrelated output', '{}', '[]'):
            with self.subTest(output=output), self.assertRaisesRegex(
                ValueError, 'GENERAL_COPIER_ACTUAL_CLI_IMPORT_REQUIRED'
            ):
                qualify_operator.cli_import_report(output)
