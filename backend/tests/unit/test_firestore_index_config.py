import json
from pathlib import Path


def _index_specs():
    path = Path(__file__).resolve().parents[3] / 'firestore.indexes.json'
    return json.loads(path.read_text())['indexes']


def _fields(index):
    return [(field.get('fieldPath'), field.get('order')) for field in index['fields']]


def test_firestore_config_declares_memory_items_canary_read_index():
    required_fields = [
        ('uid', 'ASCENDING'),
        ('generation', 'ASCENDING'),
        ('updated_at', 'DESCENDING'),
        ('__name__', 'ASCENDING'),
    ]

    assert any(
        index.get('collectionGroup') == 'memory_items'
        and index.get('queryScope') == 'COLLECTION_GROUP'
        and _fields(index) == required_fields
        for index in _index_specs()
    )


def test_firestore_config_does_not_declare_same_direction_single_field_composites():
    # Firestore auto-serves field+__name__ when both orders match (ASC+ASC /
    # DESC+DESC). Declaring those is rejected as redundant. Opposite-direction
    # pairs (e.g. updated_at DESC + __name__ ASC) are real composites and must
    # stay in the manifest (#11684).
    for index in _index_specs():
        fields = _fields(index)
        non_name = [(path, order) for path, order in fields if path != '__name__']
        name = [(path, order) for path, order in fields if path == '__name__']
        if len(non_name) != 1 or len(name) != 1:
            continue
        (_, field_order), (_, name_order) = non_name[0], name[0]
        if field_order is None or name_order is None:
            continue
        assert field_order != name_order, index


def test_firestore_config_declares_opposite_direction_universal_list_scans():
    # Prod GET /v3/memories 503ed because these were omitted from the manifest.
    required = [
        (
            'memory_items',
            'COLLECTION',
            (('updated_at', 'DESCENDING'), ('__name__', 'ASCENDING')),
        ),
        (
            'memories',
            'COLLECTION',
            (('updated_at', 'DESCENDING'), ('__name__', 'ASCENDING')),
        ),
        (
            'memories',
            'COLLECTION',
            (('created_at', 'DESCENDING'), ('__name__', 'ASCENDING')),
        ),
        (
            'memory_review_queue',
            'COLLECTION',
            (('status', 'ASCENDING'), ('__name__', 'DESCENDING')),
        ),
    ]
    specs = {
        (
            index.get('collectionGroup'),
            index.get('queryScope'),
            tuple(_fields(index)),
        )
        for index in _index_specs()
    }
    for collection, scope, fields in required:
        assert (collection, scope, fields) in specs


def test_firestore_config_declares_mcp_conversation_category_filter_index():
    required_fields = [
        ('discarded', 'ASCENDING'),
        ('status', 'ASCENDING'),
        ('structured.category', 'ASCENDING'),
        ('created_at', 'DESCENDING'),
        ('__name__', 'DESCENDING'),
    ]

    assert any(
        index.get('collectionGroup') == 'conversations'
        and index.get('queryScope') == 'COLLECTION'
        and _fields(index) == required_fields
        for index in _index_specs()
    )


def test_firestore_config_declares_screen_activity_app_filter_index():
    # Regression for #9189: the MCP get_screen_activity tool filters by appName
    # and orders/ranges on timestamp, which needs this composite index — without
    # it Firestore raises FailedPrecondition and the tool returned an opaque 500.
    required_fields = [
        ('appName', 'ASCENDING'),
        ('timestamp', 'ASCENDING'),
        ('__name__', 'ASCENDING'),
    ]

    assert any(
        index.get('collectionGroup') == 'screen_activity'
        and index.get('queryScope') == 'COLLECTION'
        and _fields(index) == required_fields
        for index in _index_specs()
    )


def _reconcile_workflow():
    path = Path(__file__).resolve().parents[3] / '.github/workflows/gcp_firestore_indexes.yml'
    return path.read_text()


# Static tripwires, not behavioral coverage: the automatic lane can only be
# exercised by a real push to main. They pin the two expressions whose failure
# modes are silent -- an empty environment binds no GitHub Environment at all
# (bypassing the prod approval), and an unresolved lock serializes nothing.
def test_reconcile_workflow_applies_a_merged_manifest_change_automatically():
    # #11684 / #11731: the manifest fix merged and changed nothing in prod for
    # ~5h because workflow_dispatch was the only trigger.
    workflow = _reconcile_workflow()
    trigger, _, _ = workflow.partition('\njobs:')
    assert '  push:\n' in trigger
    assert "branches: [ \"main\" ]" in trigger
    assert "      - 'firestore.indexes.json'" in trigger


def test_reconcile_workflow_never_binds_an_empty_environment_on_an_automatic_run():
    resolved = "${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || 'prod' }}"
    workflow = _reconcile_workflow()
    assert f'environment: {resolved}' in workflow
    assert f'group: firestore-schema-{resolved}' in workflow
    # A bare inputs reference renders empty on push.
    assert 'environment: ${{ github.event.inputs.environment }}' not in workflow
    assert 'group: deploy-backend-stack-' not in workflow


def test_reconcile_workflow_keeps_the_typed_confirmation_on_the_manual_path():
    workflow = _reconcile_workflow()
    assert 'if [[ "$EVENT_NAME" == "workflow_dispatch" ]]; then' in workflow
    assert 'APPLY_FIRESTORE_INDEXES' in workflow
    # Any trigger other than the two authorized ones must fail closed.
    assert 'elif [[ "$EVENT_NAME" != "push" ]]; then' in workflow


def test_reconcile_workflow_detects_but_never_automatically_applies_field_exemptions():
    workflow = _reconcile_workflow()
    automatic = workflow.split('\n  reconcile_composite_indexes:', 1)[1].split(
        '\n  reject_nonprod_field_exemptions:', 1
    )[0]
    destructive = workflow.split('\n  apply_field_exemptions:', 1)[1]

    assert 'reconcile_firestore_field_exemptions.py' in automatic
    assert '--check-only' in automatic
    assert '--apply' not in automatic
    assert "github.event_name == 'workflow_dispatch'" in destructive
    assert "github.event.inputs.operation == 'field-exemptions'" in destructive
    assert "github.event.inputs.environment == 'prod'" in destructive
    assert 'environment: prod' in destructive
    assert '--dry-run' in destructive
    assert '--apply' in destructive
    assert '--confirmation APPLY_FIRESTORE_FIELD_EXEMPTIONS' in destructive


def _reconcile_workflow_steps(job_name):
    import yaml

    path = Path(__file__).resolve().parents[3] / '.github/workflows/gcp_firestore_indexes.yml'
    # PyYAML parses the bare `on:` trigger key as the boolean True; the jobs we
    # care about are unaffected, so read the document as-is.
    return yaml.safe_load(path.read_text())['jobs'][job_name]['steps']


def test_field_exemption_check_only_runs_where_the_apply_operation_is_accepted():
    """The nag must never outlive the environment that can answer it.

    `reject_nonprod_field_exemptions` refuses the apply operation outside prod, so
    a check-only step that runs everywhere asserts a state non-prod databases are
    forbidden to reach and fails the development reconcile forever.
    """

    check_steps = [
        step
        for step in _reconcile_workflow_steps('reconcile_composite_indexes')
        if '--check-only' in str(step.get('run', ''))
    ]

    assert len(check_steps) == 1
    condition = str(check_steps[0].get('if', ''))
    assert condition, 'the field-exemption check must be scoped to the environment that can apply it'
    assert "== 'prod'" in condition
