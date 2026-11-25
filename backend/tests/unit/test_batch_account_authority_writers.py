"""Ratchet raw account-root writes. Runtime Commit observation covers dynamic SDK traffic."""

import ast
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from database.batch_account_authority_schema import ACCOUNT_DELETION_COLLECTION, ACCOUNT_FIELD_GROUPS

BACKEND = Path(__file__).resolve().parents[2]
OPERATIONS = frozenset({'create', 'set', 'update', 'delete'})
# Count sites by enclosing function so adding a raw call to an existing writer
# still needs review. See the reason on every admitted site.
KNOWN_RAW = {
    ('database/dream_canary.py', 'ensure_synthetic_owner.ensure', 'users', 'set'): (
        1,
        'Provisioning only for the synthetic Dream canary.',
    ),
    ('database/google_calendar_preferences.py', 'save_selection', 'users', 'update'): (
        1,
        'Exists-only update of selected calendar account preference fields.',
    ),
    ('database/play_subscriptions.py', 'set_user_fields', 'users', 'update'): (
        1,
        'Exists-only update of the Google Play purchase pointer, pending token and customer flag.',
    ),
    ('database/notifications.py', 'save_token.save_ordered', 'users', 'set'): (
        1,
        'Notification token and schedule provisioning may create a profile. Keep its existing transactions and observe root creation.',
    ),
    ('database/notifications.py', '_update_summary_schedule.update', 'users', 'update'): (
        1,
        'Notification token and schedule provisioning may create a profile. Keep its existing transactions and observe root creation.',
    ),
    ('database/notifications.py', '_update_summary_schedule.update', 'users', 'create'): (
        1,
        'Notification token and schedule provisioning may create a profile. Keep its existing transactions and observe root creation.',
    ),
    ('database/notifications.py', 'set_mentor_notification_frequency', 'users', 'set'): (
        1,
        'Notification token and schedule provisioning may create a profile. Keep its existing transactions and observe root creation.',
    ),
    ('database/referrals.py', 'claim_referral_trial.apply', 'users', 'set'): (
        1,
        'Referral transaction may provision a profile. Preserve credit and entitlement preconditions.',
    ),
    ('database/speaker_auto_enroll.py', 'publish.commit', 'users', 'update'): (
        1,
        'Exists-only speaker evidence, index or retraction metadata.',
    ),
    ('database/speaker_auto_enroll.py', 'update_privacy.commit', 'users', 'update'): (
        1,
        'Switch-off legacy write or exists-only speaker metadata update.',
    ),
    ('database/speaker_auto_enroll.py', 'update_privacy.commit', 'users', 'set'): (
        1,
        'Switch-off legacy write or exists-only speaker metadata update.',
    ),
    ('database/speaker_auto_enroll.py', 'retract_conversation.commit', 'users', 'update'): (
        1,
        'Exists-only speaker evidence, index or retraction metadata.',
    ),
    ('database/speaker_auto_enroll.py', 'revoke_person.commit', 'users', 'update'): (
        1,
        'Exists-only speaker evidence, index or retraction metadata.',
    ),
    ('database/user_data_deletion.py', 'purge_user_subtree', 'users', 'delete'): (
        1,
        'Kill-switch branch keeps the original root deletion.',
    ),
    ('database/users.py', 'record_user_platform', 'users', 'set'): (
        1,
        'Client platform registration can provision a profile. Keep its current request-path read/write budget.',
    ),
    ('database/users.py', 'set_user_cancellation_feedback', 'users', 'set'): (
        1,
        'Feedback can provision a profile. Existing observer records the upsert.',
    ),
    ('database/users.py', 'clear_byok_active', 'users', 'set'): (
        1,
        'Entitlement upsert keeps the existing BYOK transaction and can provision a profile.',
    ),
    ('database/users.py', '_set_protection_and_purge', 'users', 'set'): (
        1,
        'Kill-switch branch deliberately retains the previous merge then purge.',
    ),
    ('database/users.py', 'finalize_migration', 'users', 'update'): (
        1,
        'Kill-switch branch deliberately retains the previous protection update.',
    ),
    ('database/users.py', 'set_user_language_preference', 'users', 'set'): (
        1,
        'Language preference may provision a profile and remains observed.',
    ),
    ('database/users.py', 'set_user_onboarding_state', 'users', 'set'): (
        1,
        'Onboarding can provision a profile. Keep its current profile bootstrap contract.',
    ),
    ('database/users.py', '_s4_get_user_subscription_uncached', 'users', 'set'): (
        1,
        'Subscription fallback can provision a profile. Keep entitlement bootstrap behavior.',
    ),
    ('database/users.py', 'set_user_location_context_consent', 'users', 'set'): (
        1,
        'Independent location consent can provision a profile and remains observed.',
    ),
    ('database/users.py', 'set_default_task_integration', 'users', 'set'): (
        1,
        'Integration preference can provision a profile and remains observed.',
    ),
    ('database/voice_preferences.py', 'set_assistant_voice', 'users', 'set'): (
        1,
        'Assistant voice metadata can provision a profile and remains observed.',
    ),
    ('database/voice_profiles.py', 'add_owner_voice_confirmation.pool_in', 'users', 'create'): (
        1,
        'Voice confirmation can provision a root in its existing voice-pool transaction.',
    ),
    ('routers/dream_cohort.py', 'record_channel', 'users', 'set'): (
        1,
        'Existing Dream channel enrollment may provision a root. Commit observer covers it.',
    ),
    ('utils/email/lifecycle.py', 'set_lifecycle_opted_out', 'users', 'set'): (
        1,
        'Email lifecycle opt-out may provision a root. Keep the existing opt-out path.',
    ),
    ('scripts/canonical_apply_control_retry_emulator_test.py', '_cleanup', 'account_deletions', 'delete'): (
        1,
        'Loopback-only setup and cleanup for synthetic authority fixtures.',
    ),
    (
        'scripts/canonical_apply_control_retry_emulator_test.py',
        'main.wiping_fence_reader',
        'account_deletions',
        'set',
    ): (1, 'Loopback-only setup and cleanup for synthetic authority fixtures.'),
    ('scripts/dream_park_race_emulator_test.py', '_reset', 'users', 'set'): (
        1,
        'Loopback-only setup and cleanup for synthetic authority fixtures.',
    ),
    ('scripts/dream_park_race_emulator_test.py', 'main', 'users', 'delete'): (
        1,
        'Loopback-only setup and cleanup for synthetic authority fixtures.',
    ),
    ('scripts/fsr_people_generation_emulator_test.py', 'main', 'users', 'set'): (
        1,
        'Loopback-only setup and cleanup for synthetic authority fixtures.',
    ),
    ('scripts/held_audio_live_cost_emulator_test.py', 'main', 'account_deletions', 'delete'): (
        2,
        'Loopback-only setup and cleanup for synthetic authority fixtures.',
    ),
    ('scripts/held_audio_live_cost_emulator_test.py', 'main.failed_commit', 'account_deletions', 'set'): (
        1,
        'Loopback-only setup and cleanup for synthetic authority fixtures.',
    ),
    ('scripts/held_audio_live_cost_emulator_test.py', 'main.delete_account', 'account_deletions', 'set'): (
        1,
        'Loopback-only setup and cleanup for synthetic authority fixtures.',
    ),
    (
        'scripts/listen_lifecycle_emulator_test.py',
        '_assert_restore_fences_fanout_until_record_registration',
        'users',
        'set',
    ): (1, 'Loopback-only setup and cleanup for synthetic authority fixtures.'),
    ('scripts/listen_lifecycle_emulator_test.py', '_assert_batch_reconnect_contention', 'users', 'set'): (
        1,
        'Loopback-only setup and cleanup for synthetic authority fixtures.',
    ),
    ('scripts/staging/claim_bench.py', 'cleanup', 'users', 'delete'): (
        1,
        'Staging-only synthetic owner fixture with its own cleanup.',
    ),
    ('scripts/staging/claim_bench.py', '_seed_users', 'users', 'set'): (
        1,
        'Staging-only synthetic owner fixture with its own cleanup.',
    ),
    ('scripts/staging/replay.py', 'StagingFirestoreSeeder.seed_user', 'users', 'set'): (
        1,
        'Staging-only synthetic owner fixture with its own cleanup.',
    ),
}


def _text(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ''


def _method(call):
    return call.func.attr if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) else ''


def _ref_family(node, definitions, seen=frozenset()):
    if isinstance(node, ast.Name) and node.id not in seen:
        for value in definitions.get(node.id, ()):
            if family := _ref_family(value, definitions, seen | {node.id}):
                return family
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    name = func.id if isinstance(func, ast.Name) else _method(node)
    if name == 'account_deletion_document':
        return ACCOUNT_DELETION_COLLECTION
    if name != 'document' or not node.args or not isinstance(func, ast.Attribute):
        return None
    receiver = func.value
    if _method(receiver) == 'collection' and receiver.args:
        return _text(receiver.args[0]) if _text(receiver.args[0]) in ACCOUNT_FIELD_GROUPS else None
    receiver_name = receiver.func if isinstance(receiver, ast.Call) else None
    if isinstance(receiver_name, ast.Name) and receiver_name.id == 'account_deletion_collection':
        return ACCOUNT_DELETION_COLLECTION
    if _method(receiver) == 'account_deletion_collection':
        return ACCOUNT_DELETION_COLLECTION
    path = node.args[0]
    if isinstance(path, ast.JoinedStr):
        paths = ''.join(_text(value) or '{}' for value in path.values).split('/')
    else:
        paths = _text(path).split('/')
    return paths[0] if len(paths) == 2 and paths[0] in ACCOUNT_FIELD_GROUPS else None


def _field_roots(node, definitions, seen=frozenset()):
    if isinstance(node, ast.Name) and node.id not in seen:
        sources = definitions.get(node.id, ())
        if not sources:
            return {None}
        return set().union(*(_field_roots(value, definitions, seen | {node.id}) for value in sources))
    if isinstance(node, ast.Dict):
        roots = set()
        for key, value in zip(node.keys, node.values):
            if key is None:
                roots.update(_field_roots(value, definitions, seen))
                continue
            names = definitions.get(key.id, ()) if isinstance(key, ast.Name) else (key,)
            roots.update(_text(name).split('.', 1)[0].strip('`') or None for name in names)
            if not names:
                roots.add(None)
        return roots
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'dict' and not node.args:
        return {keyword.arg for keyword in node.keywords}
    return {None}


def _scope_nodes(scope):
    yield scope
    for child in ast.iter_child_nodes(scope):
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from _scope_nodes(child)


def raw_writes(source):
    result = Counter()

    def scan(scope, qualified, inherited):
        nodes = tuple(_scope_nodes(scope))
        definitions = defaultdict(list, {key: values[:] for key, values in inherited.items()})
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
                for target in targets:
                    if isinstance(target, ast.Name):
                        definitions[target.id].append(node.value)
        for node in nodes:
            operation = _method(node)
            if operation not in OPERATIONS or not node.args and operation != 'delete':
                continue
            family = _ref_family(node.func.value, definitions)
            data = node.args[0] if node.args else None
            if not family and node.args:
                family = _ref_family(node.args[0], definitions)
                data = node.args[1] if len(node.args) > 1 else None
            fields = _field_roots(data, definitions)
            if family and (
                operation != 'update' or fields.intersection(ACCOUNT_FIELD_GROUPS[family]) or None in fields
            ):
                result[(qualified, family, operation)] += 1
            elif not family and operation in {'set', 'update', 'create'}:
                # Wipe status is specific to the marker; catch writes in
                # transaction helpers that receive their marker as a parameter.
                if fields.intersection(ACCOUNT_FIELD_GROUPS[ACCOUNT_DELETION_COLLECTION]):
                    result[(qualified, ACCOUNT_DELETION_COLLECTION, operation)] += 1
        for node in nodes:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    name = f'{qualified}.{child.name}' if qualified else child.name
                    scan(child, name, definitions)

    scan(ast.parse(source), '', {})
    return result


def candidate_paths():
    # Discover candidates at collection time so each source is checked within
    # the normal per-test CPU budget. Include known paths to catch stale rows.
    candidates = {site[0] for site in KNOWN_RAW}
    for directory in ('database', 'routers', 'services', 'utils', 'migrations', 'scripts'):
        for path in (BACKEND / directory).rglob('*.py'):
            source = path.read_text()
            if any(token in source for token in ('users', 'account_deletion', 'wipe_status', 'wipe_auth_deleted_at')):
                candidates.add(path.relative_to(BACKEND).as_posix())
    return sorted(candidates)


@pytest.mark.parametrize('path', candidate_paths())
def test_account_authority_writer_inventory(path):
    expected = {site[1:]: count for site, (count, reason) in KNOWN_RAW.items() if site[0] == path and reason}
    assert raw_writes((BACKEND / path).read_text()) == expected


@pytest.mark.parametrize(
    'source',
    [
        "client.collection('users').document(uid).update({'private_cloud_sync_enabled': False})",
        "ref = client.document(f'users/{uid}')\npatch = {'migration_status.status': 'pending'}\ntx.update(ref, patch)",
        "ref = client.collection('users').document(uid)\nawait ref.set(metadata, merge=True)",
        "batch.delete(client.document(f'users/{uid}'))",
        "ref = account_deletion_document(uid)\ntx.update(ref, {'wipe_status': 'cancelled'})",
    ],
)
def test_planted_raw_write_changes_the_inventory(source):
    code = 'async def bypass():\n' + '\n'.join(f'    {line}' for line in source.splitlines())
    assert sum(raw_writes(code).values()) == 1
