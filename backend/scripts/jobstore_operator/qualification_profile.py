"""One immutable postSQL profile, not legacy metadata readiness acceptance."""

import json

PROFILE = 'general-copy-postsql-v2.c282.schema8'
CATALOG_PROFILE = 'general-copy-catalog-v2.c282.schema8'
SOURCE = 'c2824362c2a52925def3ef83f13c3b58487a6aa0'
TREE = 'a5c8acbd193b6b85661c9fe91759b2ec0eb80608'
CATALOG_SHA = '98a8f98bc4fac0981803497db3fd3ec0a3a82c9fe4db2071d0ee3c0fe129e4ec'
CONTRACT_SHA = '7f08d86417ec6422717b54c541a8779854572f1830afcee946b3c415b73ae4b2'
STRUCTURE_SHA = 'd12b6b5eee4d74842cf99706003ad32633e62c69e4b98a69bd44338d24315de7'
GUARD_SHA = '6309e8242ad2469cfc2076379a61a79c5dbb89aa7faf5d26dba9aeade6b67400'
READINESS_SHA = '68954c63e888dcc720f6466394d472d5a308a119a80c74622efeae2908f417bb'
SUITE_SHA = '2f4f3e64ac1b2e3e9b02da282cf232443a14ad85d9294cc7056ef3b545e79cc3'
TEST_IDS_SHA = '08bf13e46b6e0115c97fad9343e3ad12f235110594eeb25ae10ff39cdeeb2ec5'
TESTS_EXPECTED = 36


def exact(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def validate_contract(contract):
    expected = {
        'artifact_profile': PROFILE,
        'catalog_profile': CATALOG_PROFILE,
        'source_sha': SOURCE,
        'source_tree': TREE,
        'catalog_sha256': CATALOG_SHA,
        'catalog_contract_sha256': CONTRACT_SHA,
        'catalog_structure_sha256': STRUCTURE_SHA,
        'guard_sha256': GUARD_SHA,
        'readiness_sha256': READINESS_SHA,
        'suite_sha256': SUITE_SHA,
        'test_ids_sha256': TEST_IDS_SHA,
        'tests_expected': TESTS_EXPECTED,
    }
    if any(not exact(contract.get(k), v) for k, v in expected.items()):
        raise ValueError('EXACT_GENERAL_COPY_PROFILE_REQUIRED')
    return contract


def validate_suite(report):
    expected = {
        'result': 'GENERAL_COPY_FIXED_SUITE_PASS',
        'profile': PROFILE,
        'suite_sha256': SUITE_SHA,
        'test_ids_sha256': TEST_IDS_SHA,
        'tests_run': TESTS_EXPECTED,
        'tests_skipped': 0,
        'failures': 0,
        'errors': 0,
    }
    if not exact(report, expected):
        raise ValueError('EXACT_GENERAL_COPY_SUITE_WITH_ZERO_SKIPS_REQUIRED')
    return report
