import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "0123456789abcdef0123456789abcdef")

from database import conversations
from models.transcript_segment import TranscriptSegment
from utils.other.hume import (
    HumeJobModelPredictionResponseModel,
    HumePredictionEmotionResponseModel,
)


class RecordingBatch:
    """Mock Firestore batch tracking item count and commit calls."""

    def __init__(self, commit_log: list):
        self.count = 0
        self.commit_log = commit_log

    def set(self, ref, data):
        self.count += 1

    def commit(self):
        self.commit_log.append(self.count)


def setup_mock_db(commit_log: list) -> MagicMock:
    mock_db = MagicMock()
    mock_db.batch.side_effect = lambda: RecordingBatch(commit_log)
    return mock_db


def test_store_model_segments_result_850_chunks():
    """Input of 850 segments commits batches of [400, 400, 50] (exactly 3 commits, not 451)."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    segments = [
        TranscriptSegment(text=f"segment_{i}", is_user=True, start=float(i), end=float(i + 1)) for i in range(850)
    ]

    with patch.object(conversations, "db", mock_db):
        conversations.store_model_segments_result("user_123", "conv_456", "deepgram", segments)

    assert commit_log == [400, 400, 50]
    assert len(commit_log) == 3


def test_store_model_segments_result_empty():
    """Empty segments input [] performs 0 commits."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    with patch.object(conversations, "db", mock_db):
        conversations.store_model_segments_result("user_123", "conv_456", "deepgram", [])

    assert commit_log == []
    assert len(commit_log) == 0


def test_store_model_segments_result_exact_multiples():
    """Exact multiples of 400 commit exactly without empty trailing commits."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    segments_400 = [
        TranscriptSegment(text=f"segment_{i}", is_user=True, start=float(i), end=float(i + 1)) for i in range(400)
    ]

    with patch.object(conversations, "db", mock_db):
        conversations.store_model_segments_result("user_123", "conv_456", "deepgram", segments_400)

    assert commit_log == [400]
    assert len(commit_log) == 1

    commit_log.clear()
    segments_800 = [
        TranscriptSegment(text=f"segment_{i}", is_user=True, start=float(i), end=float(i + 1)) for i in range(800)
    ]

    with patch.object(conversations, "db", mock_db):
        conversations.store_model_segments_result("user_123", "conv_456", "deepgram", segments_800)

    assert commit_log == [400, 400]
    assert len(commit_log) == 2


def test_store_model_segments_result_under_chunk_size():
    """Under 400 segments commits once with the exact count."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    segments_50 = [
        TranscriptSegment(text=f"segment_{i}", is_user=True, start=float(i), end=float(i + 1)) for i in range(50)
    ]

    with patch.object(conversations, "db", mock_db):
        conversations.store_model_segments_result("user_123", "conv_456", "deepgram", segments_50)

    assert commit_log == [50]
    assert len(commit_log) == 1


def test_store_model_emotion_predictions_result_250_chunks():
    """Input of 250 predictions commits batches of [100, 100, 50] (exactly 3 commits)."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    predictions = [
        HumeJobModelPredictionResponseModel(
            time=(float(i), float(i + 1)),
            emotions=[HumePredictionEmotionResponseModel("joy", 0.9)],
        )
        for i in range(250)
    ]

    with patch.object(conversations, "db", mock_db):
        conversations.store_model_emotion_predictions_result("user_123", "conv_456", "hume", predictions)

    assert commit_log == [100, 100, 50]
    assert len(commit_log) == 3


def test_store_model_emotion_predictions_result_empty():
    """Empty predictions input [] performs 0 commits."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    with patch.object(conversations, "db", mock_db):
        conversations.store_model_emotion_predictions_result("user_123", "conv_456", "hume", [])

    assert commit_log == []
    assert len(commit_log) == 0


def test_store_model_emotion_predictions_result_exact_multiples():
    """Exact multiples of 100 commit exactly without empty trailing commits."""
    commit_log = []
    mock_db = setup_mock_db(commit_log)

    predictions_100 = [
        HumeJobModelPredictionResponseModel(
            time=(float(i), float(i + 1)),
            emotions=[HumePredictionEmotionResponseModel("joy", 0.9)],
        )
        for i in range(100)
    ]

    with patch.object(conversations, "db", mock_db):
        conversations.store_model_emotion_predictions_result("user_123", "conv_456", "hume", predictions_100)

    assert commit_log == [100]
    assert len(commit_log) == 1

    commit_log.clear()
    predictions_200 = [
        HumeJobModelPredictionResponseModel(
            time=(float(i), float(i + 1)),
            emotions=[HumePredictionEmotionResponseModel("joy", 0.9)],
        )
        for i in range(200)
    ]

    with patch.object(conversations, "db", mock_db):
        conversations.store_model_emotion_predictions_result("user_123", "conv_456", "hume", predictions_200)

    assert commit_log == [100, 100]
    assert len(commit_log) == 2
