"""desktop_prompts must survive malformed documents and store failures.

`GET /v2/desktop/prompts` is polled by every desktop client on launch and reads
admin-authored Firestore documents. Before this change a single bad document
took the whole endpoint down:

* `audience` / `trigger` / `cta` were assumed dicts, so a string or list in any
  of them raised AttributeError,
* a string `channels` value turned `channel not in channels` into a substring
  test that admitted the wrong audience, and a string `options` value was
  iterated character by character,
* `min_build` as a numeric string, or a NaN rollout percentage, raised
  TypeError/ValueError from the comparison and `int(...)` calls,
* an upstream Firestore read failure propagated as an unhandled 500.

Run with:

    PYTHONPATH=backend python3 backend/tests/unit/test_desktop_prompts_resilience.py
"""

import os
import sys
import types

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_snapshots: list = []
_read_error: BaseException | None = None


def _list_snapshots():
    if _read_error is not None:
        raise _read_error
    return _snapshots


def _load_module_under_test() -> types.ModuleType:
    """Import ``routers/desktop_prompts.py`` by path, with store/auth stubbed.

    Importing it as ``routers.desktop_prompts`` would hand back whatever copy is
    already cached in ``sys.modules`` — including one imported by a sibling test
    with the real Firestore-backed store — so the fakes below would silently not
    apply. Loading the file under a private module name keeps this suite
    order-independent and hermetic (Tier 2 of ``backend/docs/test_isolation.md``).
    """
    import importlib.util
    from pathlib import Path

    from testing.import_isolation import AutoMockModule, stub_modules

    reads = AutoMockModule('database.serving_query_reads')
    reads.list_active_desktop_prompt_snapshots = _list_snapshots

    endpoints = AutoMockModule('utils.other.endpoints')
    endpoints.get_current_user_uid = lambda: 'uid1'

    path = Path(__file__).resolve().parents[2] / 'routers' / 'desktop_prompts.py'
    spec = importlib.util.spec_from_file_location('_desktop_prompts_under_test', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with stub_modules(
        {
            'database.serving_query_reads': reads,
            'utils.other.endpoints': endpoints,
        }
    ):
        spec.loader.exec_module(module)

    return module


dp = _load_module_under_test()


class _Snap:
    def __init__(self, doc_id: str, data: object) -> None:
        self.id = doc_id
        self._data = data

    def to_dict(self) -> object:
        return self._data


def _set(snapshots=(), error=None) -> None:
    global _snapshots, _read_error
    _snapshots = list(snapshots)
    _read_error = error


def _base_doc(**over):
    doc = {'id': 'p1', 'type': 'nps', 'question': 'How likely?', 'audience': {'rollout_pct': 100}}
    doc.update(over)
    return doc


def _ids():
    return [p.id for p in dp.get_desktop_prompts(channel='stable', build=0, uid='uid1').prompts]


# --- type guards -------------------------------------------------------------


def test_as_dict_rejects_non_dict_values():
    for bad in ('nope', ['a'], 3, True, None):
        assert dp._as_dict(bad) == {}, bad
    assert dp._as_dict({'a': 1}) == {'a': 1}


def test_as_str_list_does_not_split_strings_or_iterate_ints():
    assert dp._as_str_list('stable-beta') == []
    assert dp._as_str_list(7) == []
    assert dp._as_str_list(True) == []
    assert dp._as_str_list(None) == []
    assert dp._as_str_list(['a', ' b ', '', None, 3]) == ['a', 'b', '3']


def test_as_int_rejects_bools_nan_and_garbage():
    assert dp._as_int(True, 9) == 9
    assert dp._as_int(False, 9) == 9
    assert dp._as_int(float('nan'), 9) == 9
    assert dp._as_int(float('inf'), 9) == 9
    assert dp._as_int('abc', 9) == 9
    assert dp._as_int(None, 9) == 9
    assert dp._as_int('12000', 0) == 12000
    assert dp._as_int(12.7, 0) == 12


def test_as_percent_clamps_and_defaults():
    assert dp._as_percent(150) == 100
    assert dp._as_percent(-5) == 0
    assert dp._as_percent('abc') == 100
    assert dp._as_percent(None) == 100
    assert dp._as_percent('40') == 40


# --- audience matching -------------------------------------------------------


def test_string_channels_is_not_a_substring_match():
    """'stable' must not match a malformed string channel list."""
    doc = _base_doc(audience={'channels': 'stable-beta', 'rollout_pct': 100})
    # treated as "no channel restriction", not as a substring hit
    assert dp.prompt_matches_audience(doc, 'uid1', 'beta', 0) is True
    assert dp.prompt_matches_audience(doc, 'uid1', 'stable', 0) is True


def test_int_channels_does_not_raise():
    doc = _base_doc(audience={'channels': 5, 'rollout_pct': 100})
    assert dp.prompt_matches_audience(doc, 'uid1', 'stable', 0) is True


def test_list_channels_still_filters():
    doc = _base_doc(audience={'channels': ['beta'], 'rollout_pct': 100})
    assert dp.prompt_matches_audience(doc, 'uid1', 'stable', 0) is False
    assert dp.prompt_matches_audience(doc, 'uid1', 'beta', 0) is True


def test_numeric_string_min_build_compares_instead_of_raising():
    doc = _base_doc(audience={'min_build': '12000', 'rollout_pct': 100})
    assert dp.prompt_matches_audience(doc, 'uid1', 'stable', 11000) is False
    assert dp.prompt_matches_audience(doc, 'uid1', 'stable', 13000) is True


def test_garbage_min_build_does_not_block_everyone():
    doc = _base_doc(audience={'min_build': 'abc', 'rollout_pct': 100})
    assert dp.prompt_matches_audience(doc, 'uid1', 'stable', 5) is True


def test_nan_rollout_defaults_to_full_rollout():
    doc = _base_doc(audience={'rollout_pct': float('nan')})
    assert dp.prompt_matches_audience(doc, 'uid1', 'stable', 0) is True


def test_zero_rollout_excludes_everyone():
    doc = _base_doc(audience={'rollout_pct': 0})
    assert dp.prompt_matches_audience(doc, 'uid1', 'stable', 0) is False


# --- spec construction -------------------------------------------------------


def test_spec_rejects_missing_or_invalid_identity_fields():
    assert dp.spec_from_doc({'type': 'nps', 'question': 'q'}) is None
    assert dp.spec_from_doc({'id': 'p', 'type': 'nope', 'question': 'q'}) is None
    assert dp.spec_from_doc({'id': 'p', 'type': 'nps', 'question': '   '}) is None
    assert dp.spec_from_doc({'id': '  ', 'type': 'nps', 'question': 'q'}) is None


def test_string_options_are_not_split_into_characters():
    spec = dp.spec_from_doc(_base_doc(options='yes,no'))
    assert spec is not None and spec.options == []


def test_list_options_are_capped():
    spec = dp.spec_from_doc(_base_doc(options=[f'o{i}' for i in range(12)]))
    assert spec is not None and len(spec.options) == dp.MAX_OPTIONS


def test_non_dict_trigger_and_cta_fall_back_to_defaults():
    spec = dp.spec_from_doc(_base_doc(trigger='launch', cta=['x']))
    assert spec is not None
    assert spec.trigger_kind == 'app_launch'
    assert spec.trigger_count == 0
    assert spec.cta_label is None and spec.cta_url is None


def test_max_per_day_bool_and_zero_are_normalized():
    spec = dp.spec_from_doc(_base_doc(max_per_day=True))
    assert spec is not None and spec.max_per_day == 1
    spec = dp.spec_from_doc(_base_doc(max_per_day=0))
    assert spec is not None and spec.max_per_day == 1


def test_trigger_count_never_goes_negative():
    spec = dp.spec_from_doc(_base_doc(trigger={'kind': 'session_count', 'count': -3}))
    assert spec is not None and spec.trigger_count == 0


# --- endpoint isolation ------------------------------------------------------


def test_malformed_snapshot_is_skipped_not_fatal():
    _set(
        [
            _Snap('good', _base_doc(id='good')),
            _Snap('bad', 'not-a-dict'),
            _Snap('broken', {'id': 'broken', 'type': 'nps', 'question': 'q', 'audience': 'oops'}),
        ]
    )
    assert _ids() == ['broken', 'good']


def test_store_failure_returns_empty_instead_of_raising():
    _set(error=RuntimeError('firestore unavailable'))
    assert dp.get_desktop_prompts(channel='stable', build=0, uid='uid1').prompts == []


def test_snapshot_with_none_payload_is_skipped():
    _set([_Snap('none', None), _Snap('good', _base_doc(id='good'))])
    assert _ids() == ['good']


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failures = 0
    for test in tests:
        try:
            test()
            print(f'PASS {test.__name__}')
        except AssertionError as exc:
            failures += 1
            print(f'FAIL {test.__name__}: {exc}')
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f'ERROR {test.__name__}: {type(exc).__name__}: {exc}')
    print(f'\n{len(tests) - failures}/{len(tests)} tests passed')
    sys.exit(1 if failures else 0)
