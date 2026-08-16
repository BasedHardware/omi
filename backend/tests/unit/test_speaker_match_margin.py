"""Unit tests for margin-gated speaker matching.

`select_best_match` exists because a bare threshold silently picks a winner
between two people who both fall inside it. These pin the three outcomes it has
to keep distinct: a clear match, a near-tie, and nobody close.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import numpy as np
import pytest


def _cosine_cdist(a, b, metric="cosine"):
    if metric != "cosine":
        raise ValueError(f"Unsupported test cdist metric: {metric}")
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    numerator = a @ b.T
    denominator = np.linalg.norm(a, axis=1)[:, None] * np.linalg.norm(b, axis=1)[None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        similarity = np.where(denominator == 0, 0.0, numerator / denominator)
    return 1.0 - similarity


@pytest.fixture(scope="module", autouse=True)
def _stub_optional_deps():
    created = []
    if "scipy.spatial.distance" not in sys.modules:
        scipy = sys.modules.setdefault("scipy", ModuleType("scipy"))
        spatial = ModuleType("scipy.spatial")
        distance = ModuleType("scipy.spatial.distance")
        distance.cdist = _cosine_cdist
        spatial.distance = distance
        scipy.spatial = spatial
        sys.modules["scipy.spatial"] = spatial
        sys.modules["scipy.spatial.distance"] = distance
        created.extend(["scipy.spatial", "scipy.spatial.distance"])
    for name in ("utils.executors", "utils.http_client"):
        if name not in sys.modules:
            sys.modules[name] = MagicMock()
            created.append(name)
    yield
    for name in created:
        sys.modules.pop(name, None)


def _embedding(*values):
    return np.array([values], dtype=np.float32)


class TestSelectBestMatch:
    def test_returns_the_clear_winner(self):
        from utils.stt.speaker_embedding import select_best_match

        query = _embedding(1.0, 0.0, 0.0)
        candidates = {"alex": _embedding(1.0, 0.0, 0.0), "ben": _embedding(0.0, 1.0, 0.0)}
        key, distance, ambiguous = select_best_match(query, candidates)
        assert key == "alex"
        assert distance == pytest.approx(0.0, abs=1e-5)
        assert ambiguous is False

    def test_a_near_tie_inside_the_threshold_matches_nobody(self):
        from utils.stt.speaker_embedding import select_best_match

        query = _embedding(1.0, 1.0, 0.0)
        candidates = {"alex": _embedding(1.0, 0.98, 0.0), "ben": _embedding(0.98, 1.0, 0.0)}
        key, _, ambiguous = select_best_match(query, candidates)
        assert key is None
        assert ambiguous is True

    def test_a_near_tie_still_matches_when_the_margin_is_disabled(self):
        from utils.stt.speaker_embedding import select_best_match

        query = _embedding(1.0, 1.0, 0.0)
        candidates = {"alex": _embedding(1.0, 0.98, 0.0), "ben": _embedding(0.98, 1.0, 0.0)}
        key, _, ambiguous = select_best_match(query, candidates, margin=0.0)
        assert key in {"alex", "ben"}
        assert ambiguous is False

    def test_nobody_inside_the_threshold_is_not_ambiguous(self):
        from utils.stt.speaker_embedding import select_best_match

        query = _embedding(1.0, 0.0, 0.0)
        candidates = {"alex": _embedding(-1.0, 0.0, 0.0), "ben": _embedding(0.0, -1.0, 0.0)}
        key, _, ambiguous = select_best_match(query, candidates)
        assert key is None
        assert ambiguous is False

    def test_a_sole_candidate_has_no_runner_up_to_beat(self):
        from utils.stt.speaker_embedding import select_best_match

        query = _embedding(1.0, 0.0, 0.0)
        key, _, ambiguous = select_best_match(query, {"alex": _embedding(1.0, 0.0, 0.0)})
        assert key == "alex"
        assert ambiguous is False

    def test_a_lone_candidate_inside_the_threshold_is_still_refused(self):
        from utils.stt.speaker_embedding import select_best_match

        # cos 0.6 -> distance 0.40: inside SPEAKER_MATCH_THRESHOLD, and with
        # nobody else enrolled the margin never gets to object.
        query = _embedding(1.0, 0.0)
        key, distance, ambiguous = select_best_match(query, {"alex": _embedding(0.6, 0.8)})

        assert key is None
        assert ambiguous is False
        assert distance == pytest.approx(0.40, abs=1e-6)

    def test_a_lone_candidate_close_enough_still_matches(self):
        from utils.stt.speaker_embedding import select_best_match

        # cos 0.8 -> distance 0.20.
        query = _embedding(1.0, 0.0)
        key, _, ambiguous = select_best_match(query, {"alex": _embedding(0.8, 0.6)})

        assert key == "alex"
        assert ambiguous is False

    def test_a_distant_runner_up_does_not_vouch_for_the_winner(self):
        from utils.stt.speaker_embedding import select_best_match

        # Ben is far outside the threshold, so he is no evidence that Alex is
        # the right answer -- Alex is judged as a lone candidate.
        query = _embedding(1.0, 0.0)
        candidates = {"alex": _embedding(0.6, 0.8), "ben": _embedding(-1.0, 0.0)}
        key, _, ambiguous = select_best_match(query, candidates)

        assert key is None
        assert ambiguous is False

    def test_no_candidates_matches_nothing(self):
        from utils.stt.speaker_embedding import select_best_match

        key, distance, ambiguous = select_best_match(_embedding(1.0, 0.0, 0.0), {})
        assert key is None
        assert distance == float("inf")
        assert ambiguous is False

    def test_a_dimension_mismatch_cannot_win(self):
        from utils.stt.speaker_embedding import select_best_match

        query = _embedding(1.0, 0.0, 0.0)
        candidates = {"wrong_dim": _embedding(1.0, 0.0), "alex": _embedding(1.0, 0.0, 0.0)}
        key, _, _ = select_best_match(query, candidates)
        assert key == "alex"
