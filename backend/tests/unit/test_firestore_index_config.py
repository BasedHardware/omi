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


def test_firestore_config_declares_device_routed_frame_request_queue_index():
    required_fields = [
        ('device_id', 'ASCENDING'),
        ('state', 'ASCENDING'),
        ('created_at', 'ASCENDING'),
        ('__name__', 'ASCENDING'),
    ]

    assert any(
        index.get('collectionGroup') == 'frame_requests'
        and index.get('queryScope') == 'COLLECTION'
        and _fields(index) == required_fields
        for index in _index_specs()
    )


def _reconcile_workflow():
    path = Path(__file__).resolve().parents[3] / '.github/workflows/gcp_firestore_indexes.yml'
    return path.read_text()


# Static tripwires for the push receipt and the production writer's dispatch,
# environment approval and queue. Runtime readiness is checked separately.
def test_reconcile_workflow_reports_pending_production_schema_on_main_push():
    workflow = _parse_reconcile_workflow()
    push = workflow[True]['push']
    assert push['branches'] == ['main']
    assert 'firestore.indexes.json' in push['paths']
    validation = workflow['jobs']['validate_merged_prod_indexes']
    assert 'concurrency' not in workflow
    assert validation['if'] == "github.ref == 'refs/heads/main' && github.event_name == 'push'"
    assert validation['permissions'] == {'contents': 'read'}
    assert 'environment' not in validation
    assert 'concurrency' not in validation
    assert any(
        'SCHEMA_PENDING source=$GITHUB_SHA owner=release-owner deadline=$deadline' in step.get('run', '')
        for step in validation['steps']
    )


def test_reconcile_workflow_binds_the_dispatch_environment_and_its_writer_lock():
    writer = _parse_reconcile_workflow()['jobs']['reconcile_composite_indexes']
    environment = "${{ github.event.inputs.environment }}"
    assert writer['if'] == (
        "github.ref == 'refs/heads/main' && github.event_name == 'workflow_dispatch' && "
        "github.event.inputs.operation == 'composite-indexes'"
    )
    assert writer['environment'] == environment
    assert writer['concurrency'] == {'group': f'firestore-schema-{environment}', 'cancel-in-progress': False}


def test_reconcile_workflow_keeps_the_typed_confirmation_on_the_manual_path():
    workflow = _parse_reconcile_workflow()
    assert workflow[True]['workflow_dispatch']['inputs']['confirmation']['required'] is True
    writer = workflow['jobs']['reconcile_composite_indexes']
    guard = writer['steps'][0]
    assert guard['env']['EVENT_NAME'] == "${{ github.event_name }}"
    assert guard['env']['CONFIRMATION'] == "${{ github.event.inputs.confirmation }}"
    assert (
        'if [[ "$EVENT_NAME" != "workflow_dispatch" || "$CONFIRMATION" != "APPLY_FIRESTORE_INDEXES" ]]; then'
        in guard['run']
    )


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


def _parse_reconcile_workflow():
    import yaml

    # PyYAML parses GitHub Actions' bare `on:` trigger key as boolean True.
    return yaml.safe_load(_reconcile_workflow())


def test_field_exemption_check_only_runs_where_the_apply_operation_is_accepted():
    """The nag must never outlive the environment that can answer it.

    `reject_nonprod_field_exemptions` refuses the apply operation outside prod, so
    a check-only step that runs everywhere asserts a state non-prod databases are
    forbidden to reach and fails the development reconcile forever.
    """

    check_steps = [
        step
        for step in _parse_reconcile_workflow()['jobs']['reconcile_composite_indexes']['steps']
        if '--check-only' in str(step.get('run', ''))
    ]

    assert len(check_steps) == 1
    condition = str(check_steps[0].get('if', ''))
    assert condition, 'the field-exemption check must be scoped to the environment that can apply it'
    assert "== 'prod'" in condition


def test_transactional_fresh_queries_have_indexes_with_capture_tie_breaks():
    for namespace in ('batch_pipeline_prod', 'batch_pipeline_dev'):
        for ready in (False, True):
            fields = ['owner_key', 'merge_pending', 'fresh_capture'] + (['state'] if ready else [])
            fields += ['capture_at', 'segment_id', '__name__']
            assert any(
                index['collectionGroup'] == f'{namespace}_jobs'
                and _fields(index) == [(field, 'ASCENDING') for field in fields]
                for index in _index_specs()
            )
