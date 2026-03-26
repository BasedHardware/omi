import os

TRANSCRIBE_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'transcribe.py')


def _read_transcribe_source() -> str:
    with open(TRANSCRIBE_PATH, encoding='utf-8') as f:
        return f.read()


def test_transcribe_emits_stt_degraded_status_event():
    source = _read_transcribe_source()
    assert 'status="stt_degraded"' in source


def test_transcribe_has_deepgram_degraded_branch_before_1011_close():
    source = _read_transcribe_source()
    error_pos = source.find('logger.error(f"Initial processing error: {e} {uid} {session_id}")')
    dg_branch = source.find("if stt_service == STTService.deepgram:", error_pos)
    close_branch = source.find("await websocket.close(code=websocket_close_code)", error_pos)
    assert error_pos > 0
    assert dg_branch > 0
    assert close_branch > 0
    assert dg_branch < close_branch


def test_transcribe_attempts_recovery_after_degraded_mode_entry():
    source = _read_transcribe_source()
    degraded_pos = source.find("deepgram_recovery_task = spawn(_recover_deepgram_connection())")
    degraded_event_pos = source.find('status="stt_degraded"')
    assert degraded_event_pos > 0
    assert degraded_pos > degraded_event_pos


def test_metric_dec_on_early_return_bad_uid():
    """Verify BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec() before early return on bad uid."""
    source = _read_transcribe_source()
    bad_uid_pos = source.find('reason="Bad uid"')
    assert bad_uid_pos > 0
    # dec() must appear before the close/return for bad uid
    dec_before = source.rfind('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec()', 0, bad_uid_pos)
    inc_pos = source.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.inc()')
    assert dec_before > inc_pos, "dec() must appear between inc() and bad uid early return"


def test_metric_dec_on_early_return_unsupported_language():
    """Verify BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec() before early return on unsupported language."""
    source = _read_transcribe_source()
    lang_pos = source.find('The language is not supported')
    assert lang_pos > 0
    # Search for dec() only after the bad-uid block to avoid matching bad-uid's dec()
    bad_uid_return_pos = source.find('reason="Bad uid"')
    assert bad_uid_return_pos > 0
    dec_after_bad_uid = source.find('BACKEND_LISTEN_ACTIVE_WS_CONNECTIONS.dec()', bad_uid_return_pos)
    assert (
        dec_after_bad_uid > 0 and dec_after_bad_uid < lang_pos
    ), "dec() must appear between bad-uid block and language early return"
