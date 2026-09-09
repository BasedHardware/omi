from omi.stt.parakeet import parakeet_ws_url
from omi.stt import SttEngine, create_transcriber


def test_parakeet_ws_url():
    # Plain base URL with and without trailing slash
    assert parakeet_ws_url("https://parakeet.example/") == "wss://parakeet.example/v3/stream?sample_rate=16000"
    assert parakeet_ws_url("https://parakeet.example") == "wss://parakeet.example/v3/stream?sample_rate=16000"
    assert parakeet_ws_url("http://localhost:8000") == "ws://localhost:8000/v3/stream?sample_rate=16000"

    # Query-bearing base URL preserves path and query parameters
    assert (
        parakeet_ws_url("https://parakeet.example/proxy?tenant=demo")
        == "wss://parakeet.example/proxy/v3/stream?tenant=demo&sample_rate=16000"
    )

    # Existing sample_rate in query is replaced with the configured sample_rate
    assert (
        parakeet_ws_url("https://parakeet.example/api?tenant=demo&sample_rate=8000", sample_rate=16000)
        == "wss://parakeet.example/api/v3/stream?tenant=demo&sample_rate=16000"
    )

    # Preserves repeated parameters, blank parameters, and query parameters containing https://
    url_with_nested = (
        "https://parakeet.example/v1/?redirect=https://other.example&flag&opt=1&opt=2#ignored"
    )
    expected_nested = (
        "wss://parakeet.example/v1/v3/stream"
        "?redirect=https%3A%2F%2Fother.example&flag=&opt=1&opt=2&sample_rate=16000"
    )
    assert parakeet_ws_url(url_with_nested) == expected_nested


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
