"""Handled-failure diagnostics expose only bounded categories."""

from utils.stt.failure_diagnostics import transcription_failure_categories


def _run_file_vad():
    raise FileNotFoundError('private/path/uid/token')


def test_inner_decode_failure_keeps_stage_without_message():
    try:
        _run_file_vad()
    except FileNotFoundError as error:
        try:
            raise RuntimeError('private transcript') from error
        except RuntimeError as wrapped:
            assert transcription_failure_categories(wrapped) == ('audio_decode', 'file_missing')


def test_unknown_exception_names_and_messages_do_not_escape():
    custom = type('private_uid_and_token', (Exception,), {})
    assert transcription_failure_categories(custom('private transcript')) == ('unknown', 'other')


def test_cycles_and_long_chains_are_bounded():
    error = ValueError('private')
    error.__cause__ = error
    assert transcription_failure_categories(error) == ('unknown', 'value')
    for _ in range(100):
        wrapper = TypeError('private')
        wrapper.__cause__ = error
        error = wrapper
    assert transcription_failure_categories(error) == ('unknown', 'type')


def test_implicit_context_is_categorized():
    try:
        raise PermissionError('private credential')
    except PermissionError:
        try:
            raise RuntimeError('private path')
        except RuntimeError as error:
            assert transcription_failure_categories(error) == ('unknown', 'permission')
