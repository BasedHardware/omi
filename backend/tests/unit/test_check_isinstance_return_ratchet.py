from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPOSITORY_ROOT / '.github/scripts/check_isinstance_return_ratchet.py'
SPEC = spec_from_file_location('check_isinstance_return_ratchet', SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
RATCHET = module_from_spec(SPEC)
SPEC.loader.exec_module(RATCHET)


def test_counts_only_assigned_call_isinstance_return_guards():
    source = '''
def accepted():
    value = build()
    if isinstance(value, Response):
        return value

def ignored():
    value = build()
    if isinstance(value, Response):
        raise ValueError()
    return value

def input_validation_is_ignored():
    value = build()
    if isinstance(value, str):
        return value

def boolean_validation_is_ignored():
    value = build()
    if isinstance(value, bool):
        return value
'''
    assert RATCHET.count_flow_control(source) == 1


def test_counts_response_and_result_guards_in_nested_statement_blocks():
    source = '''
def nested(enabled, lock, items, subject):
    if enabled:
        with lock:
            result = step()
            if isinstance(result, NestedResult):
                return result

    try:
        response = step()
        if isinstance(response, NestedResponse):
            return response
    except ValueError:
        fallback = step()
        if isinstance(fallback, FallbackResult):
            return fallback

    try:
        star_result = step()
        if isinstance(star_result, StarResult):
            return star_result
    except* ValueError:
        pass

    for item in items:
        loop_response = step()
        if isinstance(loop_response, LoopResponse):
            return loop_response

    match subject:
        case _:
            match_result = step()
            if isinstance(match_result, MatchResult):
                return match_result
'''
    assert RATCHET.count_flow_control(source) == 6


def test_rejects_new_file_and_allows_grandfathered_count(tmp_path):
    scan_root = tmp_path / 'backend/utils/memory'
    scan_root.mkdir(parents=True)
    target = scan_root / 'new_flow.py'
    target.write_text(
        '''
def compose():
    response = step()
    if isinstance(response, ErrorResponse):
        return response
''',
        encoding='utf-8',
    )
    counts = RATCHET.collect_counts(tmp_path, Path('backend/utils/memory'))
    relative_path = 'backend/utils/memory/new_flow.py'
    assert RATCHET.violations(counts, {}) == [f'{relative_path}: found 1, baseline allows 0']
    assert RATCHET.violations(counts, {relative_path: 1}) == []
