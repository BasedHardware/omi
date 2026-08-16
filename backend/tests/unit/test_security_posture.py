"""Posture composition must be monotonic: a narrower scope may only ever tighten."""

import itertools

from utils.security.posture import (
    InboundScreening,
    POSTURE_ENV_VAR,
    SecurityPosture,
    ToolApprovals,
    compose_security_posture,
    parse_security_posture,
    posture_from_env,
    render_security_policy_prompt,
    resolve_security_policy,
)

POSTURES = (SecurityPosture.DANGEROUS, SecurityPosture.AUTO, SecurityPosture.STRICT)


def test_composition_only_ever_tightens():
    for floor, scope in itertools.product(POSTURES, POSTURES):
        composed = compose_security_posture(floor, scope)
        assert composed.rank >= floor.rank
        assert composed.rank == max(floor.rank, scope.rank)


def test_absent_scope_leaves_the_floor_alone():
    for floor in POSTURES:
        assert compose_security_posture(floor, None) is floor


def test_a_looser_scope_cannot_lower_the_floor():
    assert compose_security_posture(SecurityPosture.STRICT, SecurityPosture.DANGEROUS) is SecurityPosture.STRICT
    assert compose_security_posture(SecurityPosture.AUTO, SecurityPosture.DANGEROUS) is SecurityPosture.AUTO


def test_postures_parse_by_name_only():
    assert parse_security_posture(' Strict ') is SecurityPosture.STRICT
    assert parse_security_posture('AUTO') is SecurityPosture.AUTO
    assert parse_security_posture('paranoid') is None
    assert parse_security_posture('') is None
    assert parse_security_posture(None) is None
    assert parse_security_posture(2) is None


def test_an_unset_or_bad_configuration_defaults_to_auto():
    assert posture_from_env({}) is SecurityPosture.AUTO
    assert posture_from_env({POSTURE_ENV_VAR: 'nonsense'}) is SecurityPosture.AUTO
    assert posture_from_env({POSTURE_ENV_VAR: 'strict'}) is SecurityPosture.STRICT
    assert posture_from_env({POSTURE_ENV_VAR: 'dangerous'}) is SecurityPosture.DANGEROUS


def test_each_posture_resolves_to_its_policy():
    assert resolve_security_policy(SecurityPosture.AUTO) == resolve_security_policy(SecurityPosture.AUTO)
    assert resolve_security_policy(SecurityPosture.AUTO).inbound_screening is InboundScreening.EXTERNAL
    assert resolve_security_policy(SecurityPosture.AUTO).tool_approvals is ToolApprovals.NONE
    assert resolve_security_policy(SecurityPosture.STRICT).tool_approvals is ToolApprovals.ALL
    assert resolve_security_policy(SecurityPosture.DANGEROUS).inbound_screening is InboundScreening.OFF


def test_the_strict_framing_names_the_distrust_requirement():
    strict = render_security_policy_prompt(resolve_security_policy(SecurityPosture.STRICT))
    assert 'Strict' in strict
    assert 'untrusted data' in strict
