"""Released desktop trial wire fields retain the permanently-disabled answers."""

import ast
from pathlib import Path

import pytest

from models.users import PlanType, TrialMetadata

BACKEND = Path(__file__).resolve().parents[2]


def _function(path, name, namespace):
    tree = ast.parse((BACKEND / path).read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    function.decorator_list = []
    # Route annotations/defaults are dependency injection, irrelevant to this pure answer.
    function.returns = None
    for arg in function.args.args:
        arg.annotation = None
    function.args.defaults = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


@pytest.mark.parametrize('uid', ['free-old-account', 'paid-account', 'byok-account', 'unreadable-account'])
def test_trial_metadata_retains_every_shipped_desktop_field_without_lookups(uid):
    namespace = {
        'TrialMetadata': TrialMetadata,
        '_effective_chat_limit': lambda plan: 30,
        'get_plan_display_name': lambda plan: 'Free' if plan == PlanType.basic else pytest.fail('unexpected plan'),
        'PlanType': PlanType,
    }
    tree = ast.parse((BACKEND / 'utils/subscription.py').read_text())
    constants = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id in {'TRIAL_LENGTH_SECONDS', 'TRIAL_FEATURES'}
            for target in node.targets
        )
    ]
    exec(compile(ast.Module(body=constants, type_ignores=[]), 'trial constants', 'exec'), namespace)
    answer = _function('utils/subscription.py', 'get_trial_metadata', namespace)(uid)
    assert answer.model_dump() == {
        'trial_started_at': None,
        'trial_ends_at': None,
        'trial_remaining_seconds': 0,
        'trial_expired': False,
        'trial_duration_seconds': 259200,
        'trial_features': [
            'unlimited_listening',
            'unlimited_transcription',
            'unlimited_memories',
            'unlimited_insights',
            '30_chat_questions_per_month',
        ],
        'plan_after_trial': 'Free',
    }


@pytest.mark.parametrize('platform', [None, 'desktop', 'macos', 'windows', 'ios', 'android'])
def test_paywall_status_remains_false_without_any_entitlement_or_cache_lookup(platform):
    from pydantic import BaseModel

    class Response(BaseModel):
        paywalled: bool

    answer = _function('routers/users.py', 'get_user_paywall_status', {'PaywallStatusResponse': Response})
    assert answer('any-user', platform, platform).model_dump() == {'paywalled': False}
