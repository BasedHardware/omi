"""Bounded validation for model-authored promotion graph plans."""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from models.memory_promotion import (
    GraphRelationEndpoint,
    PROMOTION_GRAPH_ARGUMENT_KEY_MAX_LENGTH,
    PROMOTION_GRAPH_ARGUMENT_MAX_COUNT,
    PROMOTION_GRAPH_ARGUMENTS_MAX_DEPTH,
    PROMOTION_GRAPH_ARGUMENTS_MAX_JSON_BYTES,
    PROMOTION_GRAPH_PREDICATE_MAX_LENGTH,
    PROMOTION_GRAPH_SUBJECT_MAX_LENGTH,
    PromotionGraphPlan,
    build_promotion_admission_receipt,
    valid_promotion_admission,
)


def test_typed_graph_endpoint_rejects_unknown_desktop_node_type():
    with pytest.raises(ValidationError, match="node_type"):
        GraphRelationEndpoint(label="Omi", node_type="account")


def _plan(**overrides):
    values = {
        "subject_entity_id": "user",
        "predicate": "remembered_fact",
        "arguments": {"statement": "The user prefers tea."},
    }
    values.update(overrides)
    return PromotionGraphPlan(**values)


def test_graph_plan_accepts_exact_identifier_key_and_count_bounds_with_json_values():
    supported_values = [
        None,
        True,
        7,
        1.25,
        "Seattle",
        ["nested", {"active": False}],
    ]
    arguments = {
        f"slot_{index:02d}".ljust(PROMOTION_GRAPH_ARGUMENT_KEY_MAX_LENGTH, "x"): supported_values[
            index % len(supported_values)
        ]
        for index in reversed(range(PROMOTION_GRAPH_ARGUMENT_MAX_COUNT))
    }

    plan = _plan(
        subject_entity_id="s" * PROMOTION_GRAPH_SUBJECT_MAX_LENGTH,
        predicate="p" * PROMOTION_GRAPH_PREDICATE_MAX_LENGTH,
        arguments=arguments,
    )

    assert list(plan.arguments) == sorted(arguments)
    assert len(plan.arguments) == PROMOTION_GRAPH_ARGUMENT_MAX_COUNT
    assert plan.arguments == json.loads(json.dumps(plan.arguments))


def test_graph_plan_preserves_whitespace_normalization_and_stable_hashing():
    first = _plan(
        subject_entity_id=" user ",
        predicate=" prefers ",
        arguments={" location ": "Seattle", "activity": "hiking"},
    )
    second = _plan(
        subject_entity_id="user",
        predicate="prefers",
        arguments={"activity": "hiking", "location": "Seattle"},
    )

    assert first.arguments == {"activity": "hiking", "location": "Seattle"}
    assert first.plan_hash == second.plan_hash


@pytest.mark.parametrize(
    ("field", "limit", "message"),
    [
        (
            "subject_entity_id",
            PROMOTION_GRAPH_SUBJECT_MAX_LENGTH,
            "promotion graph subject_entity_id must be at most 200 characters",
        ),
        (
            "predicate",
            PROMOTION_GRAPH_PREDICATE_MAX_LENGTH,
            "promotion graph predicate must be at most 64 characters",
        ),
    ],
)
def test_graph_plan_rejects_oversized_identifiers(field: str, limit: int, message: str):
    with pytest.raises(ValidationError, match=message):
        _plan(**{field: "x" * (limit + 1)})


def test_graph_plan_rejects_too_many_arguments():
    arguments = {f"slot_{index}": index for index in range(PROMOTION_GRAPH_ARGUMENT_MAX_COUNT + 1)}

    with pytest.raises(ValidationError, match="promotion graph plan supports at most 16 arguments"):
        _plan(arguments=arguments)


def test_graph_plan_rejects_oversized_keys_at_any_object_depth():
    arguments = {"outer": {"x" * (PROMOTION_GRAPH_ARGUMENT_KEY_MAX_LENGTH + 1): "value"}}

    with pytest.raises(ValidationError, match="promotion graph argument keys must be at most 64 characters"):
        _plan(arguments=arguments)


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({" ": "value"}, "promotion graph argument keys must not be blank"),
        ({"slot": "first", " slot ": "second"}, "promotion graph argument keys must be unique after trimming"),
    ],
)
def test_graph_plan_rejects_ambiguous_top_level_argument_keys(arguments, message: str):
    with pytest.raises(ValidationError, match=message):
        _plan(arguments=arguments)


def test_graph_plan_json_payload_has_an_exact_encoded_byte_boundary():
    empty_payload_size = len(json.dumps({"value": ""}, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    value_at_limit = "x" * (PROMOTION_GRAPH_ARGUMENTS_MAX_JSON_BYTES - empty_payload_size)

    assert _plan(arguments={"value": value_at_limit}).arguments["value"] == value_at_limit
    with pytest.raises(
        ValidationError,
        match="promotion graph arguments JSON payload must be at most 8192 bytes",
    ):
        _plan(arguments={"value": value_at_limit + "x"})


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (
            datetime(2026, 7, 28),
            "promotion graph arguments must contain only JSON values",
        ),
        (
            ("tuple",),
            "promotion graph arguments must contain only JSON values",
        ),
        (
            {1: "non-string key"},
            "promotion graph argument object keys must be strings",
        ),
        (
            float("nan"),
            "promotion graph argument numbers must be finite JSON numbers",
        ),
        (
            float("inf"),
            "promotion graph argument numbers must be finite JSON numbers",
        ),
    ],
)
def test_graph_plan_rejects_values_outside_strict_json(value, message: str):
    with pytest.raises(ValidationError, match=message):
        _plan(arguments={"value": value})


def test_graph_plan_json_nesting_has_an_exact_depth_boundary():
    value = "leaf"
    for _ in range(PROMOTION_GRAPH_ARGUMENTS_MAX_DEPTH):
        value = [value]

    assert _plan(arguments={"value": value}).arguments["value"] == value
    value = [value]
    with pytest.raises(
        ValidationError,
        match="promotion graph arguments exceed maximum JSON nesting depth of 8",
    ):
        _plan(arguments={"value": value})


def test_graph_plan_rejects_cyclic_containers_with_a_validation_error():
    value = []
    value.append(value)

    with pytest.raises(ValidationError, match="promotion graph arguments must not contain cyclic containers"):
        _plan(arguments={"value": value})


def test_promotion_admission_fails_closed_on_pathological_stored_arguments():
    graph_plan = _plan(arguments={"1": "numeric-looking key", "statement": "The user prefers tea."})
    receipt = build_promotion_admission_receipt(
        memory_id="memory-1",
        source_item_revision=1,
        output_content_hash="content-hash",
        evidence_ids=["evidence-1"],
        graph_plan=graph_plan,
        supersedes=[],
    )

    assert (
        valid_promotion_admission(
            memory_id="memory-1",
            source_item_revision=1,
            output_content_hash="content-hash",
            evidence_ids=["evidence-1"],
            subject_entity_id=graph_plan.subject_entity_id,
            predicate=graph_plan.predicate,
            arguments={1: "numeric-looking key", "statement": "The user prefers tea."},
            supersedes=[],
            promotion={
                "graph_plan": graph_plan.model_dump(mode="json"),
                "admission_receipt": receipt.model_dump(mode="json"),
            },
        )
        is False
    )
