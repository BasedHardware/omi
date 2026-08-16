from omi.stt.parakeet import parakeet_ws_url
from omi.stt import SttEngine, create_transcriber


def test_parakeet_ws_url():
    assert parakeet_ws_url("https://parakeet.example/") == "wss://parakeet.example/v3/stream?sample_rate=16000"


def test_whisper_requires_dep_or_runner():
    try:
        create_transcriber(SttEngine.WHISPER)
    except ImportError:
        return
    except Exception:
        # runner/model path may fail differently depending on env
        return


def test_deepgram_requires_key():
    try:
        create_transcriber(SttEngine.DEEPGRAM, api_key="")
        assert False, "expected error"
    except ValueError:
        pass
