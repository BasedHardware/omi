"""Usage counters written with `set(merge=True)` must land NESTED, not under a dotted field name.

`record_llm_usage` and its siblings build keys like `chat.gpt-4o.input_tokens` — the module's own comment
says "Use nested field paths" and sanitises `.` out of the model name precisely so the remaining dots are
separators. But those dicts are written with `set(..., merge=True)`, and Firestore treats a dot as a
field PATH only in `update()`; in `set()` it is a literal character.

Measured against the Firestore emulator before this fix, after two calls of 5 and 7 input tokens:

    {'date': '2026-01-01', 'chat.model-x.input_tokens': 12, ...}

The counter is right and the shape is not. Every reader walks `feature -> model -> counter`
(`_aggregate_summary`, `get_usage_summary`, `get_plan_usage_report`) and skips a value that is not a
dict, so usage summaries read empty on Firestore.
"""

from __future__ import annotations

from typing import Any, Dict

from google.cloud import firestore

from database.llm_usage import _nested


def test_a_dotted_path_becomes_a_nested_map():
    assert _nested({'chat.gpt-4o.input_tokens': 3}) == {'chat': {'gpt-4o': {'input_tokens': 3}}}


def test_a_key_without_dots_is_left_alone():
    assert _nested({'date': '2026-01-01'}) == {'date': '2026-01-01'}


def test_paths_that_share_a_prefix_merge_into_one_branch():
    """The whole point: three counters for one model must be three keys of one map, not three maps."""
    nested = _nested(
        {
            'chat.gpt-4o.input_tokens': 1,
            'chat.gpt-4o.output_tokens': 2,
            'chat.gpt-4o.call_count': 3,
            'chat.claude.call_count': 4,
        }
    )

    assert nested == {
        'chat': {
            'gpt-4o': {'input_tokens': 1, 'output_tokens': 2, 'call_count': 3},
            'claude': {'call_count': 4},
        }
    }


def test_sentinels_are_carried_through_untouched():
    """The values are `firestore.Increment`, and they must reach the leaf as themselves — nesting must
    not stringify or copy them, or the write stops being an atomic increment."""
    increment = firestore.Increment(2)

    nested = _nested({'chat.gpt-4o.input_tokens': increment})

    assert nested['chat']['gpt-4o']['input_tokens'] is increment


def test_a_leaf_and_a_branch_at_the_same_path_do_not_lose_the_branch():
    """`plan_usage.<plan>._metadata.last_cost_status` is a leaf while
    `plan_usage.<plan>._metadata.cost_status_counts.missing` is a branch under the same parent."""
    nested = _nested(
        {
            'plan_usage.free._metadata.last_cost_status': 'missing',
            'plan_usage.free._metadata.cost_status_counts.missing': 1,
        }
    )

    metadata = nested['plan_usage']['free']['_metadata']
    assert metadata['last_cost_status'] == 'missing'
    assert metadata['cost_status_counts'] == {'missing': 1}


# --- the real writer -------------------------------------------------------------------------------


class _Ref:
    """A document reference that records the last write and can be walked like Firestore's."""

    def __init__(self) -> None:
        self.written: Dict[str, Any] = {}
        self.merge: Any = None

    def set(self, data: Dict[str, Any], merge: bool = False) -> None:
        self.written = data
        self.merge = merge

    def get(self, *_args: Any, **_kwargs: Any) -> Any:
        return type('S', (), {'exists': False, 'to_dict': staticmethod(lambda: {})})()

    def collection(self, *_args: Any) -> "_Collection":
        return _Collection(self)


class _Collection:
    def __init__(self, ref: "_Ref") -> None:
        self._ref = ref

    def document(self, *_args: Any) -> "_Ref":
        return self._ref


class _Client:
    def __init__(self, ref: "_Ref") -> None:
        self._ref = ref

    def collection(self, *_args: Any) -> _Collection:
        return _Collection(self._ref)


def test_record_llm_usage_writes_a_nested_document():
    from database.llm_usage import record_llm_usage

    ref = _Ref()
    record_llm_usage('user-1', 'chat', 'gpt-4o', 5, 7, firestore_client=_Client(ref))

    assert ref.merge is True
    assert [k for k in ref.written if '.' in k] == [], 'no field name may contain a literal dot'
    assert set(ref.written['chat']['gpt-4o']) == {'input_tokens', 'output_tokens', 'call_count'}
