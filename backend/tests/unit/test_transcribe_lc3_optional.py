from pathlib import Path

TRANSCRIBE_SOURCE = Path(__file__).resolve().parents[2] / 'routers' / 'transcribe.py'


def _read_source() -> str:
    return TRANSCRIBE_SOURCE.read_text(encoding='utf-8')


def test_lc3_import_is_optional():
    source = _read_source()

    assert 'try:\n    import lc3  # lc3py' in source
    assert 'except Exception as e:\n    lc3 = None\n    _LC3_IMPORT_ERROR = e' in source
    assert 'else:\n    _LC3_IMPORT_ERROR = None' in source


def test_lc3_codec_closes_cleanly_when_dependency_missing():
    source = _read_source()

    assert "elif codec == 'lc3':" in source
    assert 'if lc3 is None:' in source
    assert 'LC3 codec requested but lc3py is not installed' in source
    assert 'await websocket.close(code=websocket_close_code, reason="LC3 codec is not available")' in source
    assert '_get_lc3().Decoder(lc3_frame_duration_us, sample_rate)' in source
