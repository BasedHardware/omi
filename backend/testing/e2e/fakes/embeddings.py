"""
Fake HTTP endpoints for speaker embedding, diarization, and VAD services.

These are ML services called via HTTP POST by the backend during
conversation processing. We return deterministic embeddings/vad results.
"""

import json

# Fake speaker embedding response — 192-dim vector (wespeaker-voxceleb-resnet34-LM)
FAKE_EMBEDDING = [0.01] * 192

# Fake VAD response
FAKE_VAD_RESPONSE = {
    "is_speech": True,
    "confidence": 0.95,
    "segments": [{"start": 0.0, "end": 5.0, "is_speech": True}],
}


def make_embedding_response(text: str = None) -> dict:
    """Build a fake /v2/embedding response."""
    return {"embedding": FAKE_EMBEDDING, "text_hash": hash(text or "") % (2**32)}


def make_vad_response(audio_bytes_len: int = 0) -> dict:
    """Build a fake /v1/vad response."""
    return dict(FAKE_VAD_RESPONSE)


def configure_embedding_fakes(httpserver):
    """
    Register fake embedding/diarization/VAD handlers on pytest-httpserver.

    Endpoints faked:
      - POST /v2/embedding  (speaker embedding)
      - POST /v1/diarization (speaker diarization)
      - POST /v1/vad         (voice activity detection)
      - POST /v1/speaker-identification (speaker matching)
    """

    # Speaker embedding (hosted diarizer)
    httpserver.expect_request("/v2/embedding", method="POST").respond_with_json(
        make_embedding_response(), status=200, content_type="application/json"
    )

    # Diarization
    httpserver.expect_request("/v1/diarization", method="POST").respond_with_json(
        {"segments": [{"speaker": "SPEAKER_00", "start": 0.0, "end": 10.0}]},
        status=200,
        content_type="application/json",
    )

    # VAD
    httpserver.expect_request("/v1/vad", method="POST").respond_with_json(
        make_vad_response(), status=200, content_type="application/json"
    )

    # Speaker identification
    httpserver.expect_request("/v1/speaker-identification", method="POST").respond_with_json(
        {"matched_speaker_id": None, "confidence": 0.0, "candidates": []},
        status=200,
        content_type="application/json",
    )
