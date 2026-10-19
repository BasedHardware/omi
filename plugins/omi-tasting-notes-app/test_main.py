"""Hermetic tests for the Omi Tasting Notes plugin.

Standard library only: fastapi, pydantic, and the Omi plugin SDK are stubbed
when not importable, so the suite runs under plain `python3` (the CI lane in
.github/checks-manifest.yaml). When real fastapi/pydantic are present they are
used, which additionally exercises real request validation.

Covers the review blockers: JSON-null optionals must take defaults, the
webhook must accept the Omi Conversation payload with uid as a query
parameter, and ambient candidates must be reachable (list_candidates) and
persist on confirm.
"""

import asyncio
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parent

# Storage must point at a temp dir before main is imported (DATA_DIR is read
# at import time).
_TMP = tempfile.mkdtemp(prefix="tasting-notes-test-")
os.environ["TASTING_DATA_DIR"] = _TMP

sys.path.insert(0, str(APP_DIR))

# ---------------------------------------------------------------------------
# Dependency stubs (only installed for modules that fail to import)
# ---------------------------------------------------------------------------

_stubs: dict[str, types.ModuleType] = {}


def _stub_fastapi() -> types.ModuleType:
    mod = types.ModuleType("fastapi")

    class _FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda fn: fn

        def post(self, *args, **kwargs):
            return lambda fn: fn

        def exception_handler(self, *args, **kwargs):
            return lambda fn: fn

    mod.FastAPI = _FastAPI
    mod.Query = lambda *args, **kwargs: None  # noqa: E731
    mod.Request = type("Request", (), {})

    responses = types.ModuleType("fastapi.responses")

    class _HTMLResponse:
        pass

    class _JSONResponse:
        def __init__(self, content=None, status_code=200, **kwargs):
            self.content = content
            self.status_code = status_code

    responses.HTMLResponse = _HTMLResponse
    responses.JSONResponse = _JSONResponse

    exceptions = types.ModuleType("fastapi.exceptions")

    class _RequestValidationError(Exception):
        def __init__(self, errors=None):
            self._errors = errors or []

        def errors(self):
            return self._errors

    exceptions.RequestValidationError = _RequestValidationError

    _stubs["fastapi"] = mod
    _stubs["fastapi.responses"] = responses
    _stubs["fastapi.exceptions"] = exceptions
    return mod


def _stub_pydantic() -> types.ModuleType:
    mod = types.ModuleType("pydantic")

    def _Field(default=None, **kwargs):
        return default

    def _field_validator(*fields, **kwargs):
        def deco(fn):
            try:
                fn._stub_validator_fields = fields
            except AttributeError:
                pass
            return fn

        return deco

    def _model_validator(*args, **kwargs):
        return lambda fn: fn

    class _BaseModel:
        def __init__(self, **data):
            cls = type(self)
            # Run mode="before" field validators registered on the class.
            for klass in cls.__mro__:
                for attr in vars(klass).values():
                    fields = getattr(attr, "_stub_validator_fields", None)
                    if not fields:
                        continue
                    func = attr.__func__ if isinstance(attr, classmethod) else attr
                    if not callable(func):
                        continue
                    for field_name in fields:
                        if field_name in data:
                            data[field_name] = func(cls, data[field_name])
            # Class-level defaults for omitted fields.
            for klass in reversed(cls.__mro__):
                for key, value in vars(klass).items():
                    if (
                        key.startswith("_")
                        or key in data
                        or isinstance(value, classmethod)
                        or callable(value)
                    ):
                        continue
                    data[key] = None if value is Ellipsis else value
            for key, value in data.items():
                setattr(self, key, value)

        @classmethod
        def model_validate(cls, data):
            if isinstance(data, dict):
                # Same semantics as _NullMeansDefault.drop_nulls: explicit
                # nulls take field defaults.
                return cls(**{k: v for k, v in data.items() if v is not None})
            return cls()

        def model_dump(self, **kwargs):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    mod.BaseModel = _BaseModel
    mod.Field = _Field
    mod.field_validator = _field_validator
    mod.model_validator = _model_validator
    _stubs["pydantic"] = mod
    return mod


def _stub_omi_sdk() -> types.ModuleType:
    sdk = types.ModuleType("omi_plugin_sdk")
    models = types.ModuleType("omi_plugin_sdk.models")

    class _TranscriptSegment:
        def __init__(self, text="", is_user=True, **kwargs):
            self.text = text
            self.is_user = is_user

    class _Conversation:
        """Minimal stand-in: transcript_segments + get_transcript()."""

        def __init__(
            self,
            transcript_segments=None,
            id=None,
            discarded=False,
            created_at=None,
            **kwargs,
        ):
            self.transcript_segments = transcript_segments or []
            self.id = id
            self.discarded = discarded
            self.created_at = created_at

        def get_transcript(self):
            parts = []
            for segment in self.transcript_segments:
                if isinstance(segment, dict):
                    text = segment.get("text", "")
                else:
                    text = getattr(segment, "text", "")
                if text:
                    parts.append(str(text))
            return "\n".join(parts)

    models.TranscriptSegment = _TranscriptSegment
    models.Conversation = _Conversation
    sdk.models = models
    _stubs["omi_plugin_sdk"] = sdk
    _stubs["omi_plugin_sdk.models"] = models
    return sdk


# The Omi plugin SDK is used for real whenever it is importable: from the
# repo's plugins/omi-plugin-sdk/src tree (CI lane) or an installed copy
# (local dev). It is stubbed only as a last resort, because FastAPI needs the
# real Conversation model to build the webhook route.
_SDK_SRC = APP_DIR.parent / "omi-plugin-sdk" / "src"
if _SDK_SRC.is_dir():
    sys.path.insert(0, str(_SDK_SRC))

try:
    from omi_plugin_sdk import models as _sdk_models  # noqa: F401

    REAL_SDK = True
except Exception:
    REAL_SDK = False
    _stub_omi_sdk()

for _name, _builder in (
    ("fastapi", _stub_fastapi),
    ("pydantic", _stub_pydantic),
):
    try:
        __import__(_name)
    except ImportError:
        _builder()

REAL_PYDANTIC = "pydantic" not in _stubs

with patch.dict(sys.modules, _stubs):
    import main as tasting_main  # noqa: E402


def _conversation(text: str, **kwargs):
    if REAL_SDK:
        from datetime import datetime, timezone

        segment = _sdk_models.TranscriptSegment(
            text=text, is_user=True, start=0.0, end=1.0
        )
        return _sdk_models.Conversation(
            created_at=datetime.now(timezone.utc),
            structured=_sdk_models.Structured(),
            transcript_segments=[segment],
            **kwargs,
        )
    segments = [{"text": text, "is_user": True}]
    return tasting_main.Conversation(transcript_segments=segments, **kwargs)


def _run(coro):
    return asyncio.run(coro)


UID = "test-user-1"

BAROLO_TRANSCRIPT = (
    "We just got to the winery in Piedmont and the tasting room is beautiful. "
    "This Barolo Riserva 2019 has such tar and roses on the bouquet, firm tannins, "
    "long finish. I'd give it 94 points. We should definitely buy a case to take home."
)

COFFEE_TRANSCRIPT = (
    "At the roastery cupping this morning. The single origin Ethiopian pour over "
    "has bright bergamot on the nose, 4.5 stars from me, super clean finish."
)

WHISKEY_TRANSCRIPT = (
    "At the distillery tasting, tried a single malt scotch at cask strength, "
    "neat. Peated, long finish. 92 points, worth buying a bottle."
)

LUNCH_TRANSCRIPT = (
    "Grabbed lunch downtown and talked about the quarterly roadmap. "
    "The new hire starts Monday. We should revisit the budget next week."
)


class _BaseTest(unittest.TestCase):
    def setUp(self):
        for path in Path(_TMP).glob("*.json"):
            path.unlink()


class TestDetection(_BaseTest):
    def test_detect_wine_conversation(self):
        beverage, score = tasting_main.detect_tasting(BAROLO_TRANSCRIPT)
        self.assertEqual(beverage, "wine")
        self.assertGreaterEqual(score, tasting_main.TASTING_DETECT_THRESHOLD)

    def test_detect_coffee_conversation(self):
        beverage, score = tasting_main.detect_tasting(COFFEE_TRANSCRIPT)
        self.assertEqual(beverage, "coffee")
        self.assertGreaterEqual(score, tasting_main.TASTING_DETECT_THRESHOLD)

    def test_detect_whiskey_conversation(self):
        beverage, score = tasting_main.detect_tasting(WHISKEY_TRANSCRIPT)
        self.assertEqual(beverage, "whiskey")

    def test_no_detection_for_ordinary_conversation(self):
        beverage, _ = tasting_main.detect_tasting(LUNCH_TRANSCRIPT)
        self.assertIsNone(beverage)

    def test_single_wine_mention_is_not_a_tasting(self):
        beverage, _ = tasting_main.detect_tasting(
            "We had wine with dinner and talked taxes."
        )
        self.assertIsNone(beverage)

    def test_coffee_chatter_without_tasting_terms_is_ignored(self):
        # "coffee" + "espresso" alone must not file a tasting.
        beverage, _ = tasting_main.detect_tasting(
            "Grabbed a coffee, she had an espresso, then we talked roadmap."
        )
        self.assertIsNone(beverage)

    def test_burgundy_the_colour_is_not_wine(self):
        beverage, _ = tasting_main.detect_tasting(
            "We painted the nursery burgundy and had wine with dinner."
        )
        self.assertIsNone(beverage)


class TestScoreParsing(_BaseTest):
    def test_parse_100_point_score(self):
        self.assertEqual(tasting_main.parse_score("I'd give it 94 points"), 94.0)

    def test_parse_star_score_normalized(self):
        self.assertEqual(tasting_main.parse_score("4.5 stars from me"), 90.0)

    def test_parse_ten_point_score_normalized(self):
        self.assertEqual(tasting_main.parse_score("solid 9/10"), 90.0)

    def test_parse_score_clamped(self):
        self.assertEqual(tasting_main.parse_score("110 points, perfect"), 100.0)

    def test_parse_score_none(self):
        self.assertIsNone(tasting_main.parse_score("it was nice"))

    def test_star_count_does_not_read_trailing_digit(self):
        # "15 stars" must not be read as 5 stars = 100; an unknown scale
        # yields no score rather than a bogus one.
        self.assertIsNone(tasting_main.parse_score("gave it 15 stars"))


class TestVerdict(_BaseTest):
    def test_infer_buy_verdict(self):
        self.assertEqual(
            tasting_main.infer_verdict("We should buy a case to take home"), "buy"
        )

    def test_infer_skip_verdict(self):
        self.assertEqual(tasting_main.infer_verdict("I wouldn't buy this one"), "skip")

    def test_skip_wins_over_buy_on_negation(self):
        self.assertEqual(tasting_main.infer_verdict("wouldn't buy, not worth it"), "skip")

    def test_negated_buy_is_not_a_buy(self):
        self.assertIsNone(tasting_main.infer_verdict("no way we're buying a case"))

    def test_not_taking_home_is_not_a_buy(self):
        self.assertIsNone(tasting_main.infer_verdict("definitely not taking home"))

    def test_not_worth_missing_is_not_a_skip(self):
        self.assertIsNone(tasting_main.infer_verdict("this one is not worth missing"))

    def test_not_worth_is_a_skip(self):
        self.assertEqual(tasting_main.infer_verdict("not worth it, honestly"), "skip")

    def test_no_verdict_without_purchase_language(self):
        self.assertIsNone(tasting_main.infer_verdict("lovely tannins, long finish"))


class TestNullCoercion(_BaseTest):
    """The Omi backend forwards every non-required manifest param, sending
    JSON null for unset ones. Nulls must take defaults, never 422."""

    def test_drop_nulls(self):
        cleaned = tasting_main._NullMeansDefault.drop_nulls(
            {"uid": "u", "limit": None, "beverage_type": None}
        )
        self.assertEqual(cleaned, {"uid": "u"})

    @unittest.skipUnless(REAL_PYDANTIC, "requires real pydantic validation")
    def test_list_tastings_null_limit_takes_default(self):
        req = tasting_main.ListTastingsRequest.model_validate(
            {"uid": UID, "limit": None, "beverage_type": None}
        )
        self.assertEqual(req.limit, 10)
        self.assertIsNone(req.beverage_type)

    @unittest.skipUnless(REAL_PYDANTIC, "requires real pydantic validation")
    def test_log_tasting_all_optionals_null(self):
        req = tasting_main.LogTastingRequest.model_validate(
            {
                "uid": UID,
                "beverage_type": None,
                "name": None,
                "score_100": None,
                "verdict": None,
                "notes": None,
            }
        )
        self.assertEqual(req.beverage_type, "wine")
        self.assertIsNone(req.score_100)

    @unittest.skipUnless(REAL_PYDANTIC, "requires real pydantic validation")
    def test_list_candidates_null_limit_takes_default(self):
        req = tasting_main.ListCandidatesRequest.model_validate(
            {"uid": UID, "limit": None}
        )
        self.assertEqual(req.limit, 10)

    @unittest.skipUnless(REAL_PYDANTIC, "requires real pydantic validation")
    def test_confirm_candidate_null_corrections(self):
        req = tasting_main.ConfirmCandidateRequest.model_validate(
            {
                "uid": UID,
                "candidate_id": "abc123",
                "name": None,
                "score_100": None,
                "verdict": None,
            }
        )
        self.assertEqual(req.candidate_id, "abc123")
        self.assertIsNone(req.score_100)

    def test_coerce_limit(self):
        coerce = tasting_main.ListTastingsRequest.coerce_limit
        self.assertEqual(coerce(None), 10)
        self.assertEqual(coerce("5"), 5)
        self.assertEqual(coerce(25), 25)

    @unittest.skipUnless(REAL_PYDANTIC, "requires real pydantic validation")
    def test_invalid_beverage_still_rejected(self):
        with self.assertRaises(Exception):
            tasting_main.LogTastingRequest.model_validate(
                {"uid": UID, "beverage_type": "kombucha"}
            )

    @unittest.skipUnless(REAL_PYDANTIC, "requires real pydantic validation")
    def test_out_of_range_score_still_rejected(self):
        with self.assertRaises(Exception):
            tasting_main.LogTastingRequest.model_validate(
                {"uid": UID, "score_100": 150}
            )

    @unittest.skipUnless(REAL_PYDANTIC, "requires real pydantic validation")
    def test_out_of_range_limit_still_rejected(self):
        with self.assertRaises(Exception):
            tasting_main.ListTastingsRequest.model_validate({"uid": UID, "limit": 0})


class TestWebhook(_BaseTest):
    def test_webhook_detects_and_stores_candidate(self):
        body = _run(
            tasting_main.tasting_candidate(_conversation(BAROLO_TRANSCRIPT), UID)
        )
        self.assertTrue(body["detected"])
        self.assertEqual(body["beverage_type"], "wine")
        self.assertEqual(body["score_100"], 94.0)
        self.assertEqual(body["verdict"], "buy")
        self.assertTrue(body["needs_review"])
        self.assertIn("candidate_id", body)

    def test_webhook_ignores_non_tasting(self):
        body = _run(
            tasting_main.tasting_candidate(_conversation(LUNCH_TRANSCRIPT), UID)
        )
        self.assertFalse(body["detected"])

    def test_webhook_skips_discarded_conversations(self):
        body = _run(
            tasting_main.tasting_candidate(
                _conversation(BAROLO_TRANSCRIPT, discarded=True), UID
            )
        )
        self.assertFalse(body["detected"])

    def test_webhook_uses_conversation_id(self):
        body = _run(
            tasting_main.tasting_candidate(
                _conversation(BAROLO_TRANSCRIPT, id="conv-9"), UID
            )
        )
        self.assertTrue(body["detected"])
        data = tasting_main._load_user(UID)
        self.assertEqual(data["candidates"][0]["conversation_id"], "conv-9")


class TestChatTools(_BaseTest):
    def _log(self, **kwargs):
        payload = {"uid": UID}
        payload.update(kwargs)
        req = tasting_main.LogTastingRequest.model_validate(payload)
        return _run(tasting_main.log_tasting(req))

    def test_log_tasting_round_trip(self):
        res = self._log(
            beverage_type="wine",
            name="Barolo Riserva",
            producer="G.D. Vajra",
            vintage="2019",
            region="Piedmont, Italy",
            varietal="Nebbiolo",
            nose="tar and roses",
            palate="firm tannins, cherry",
            finish="long",
            score_100=94,
            verdict="buy",
        )
        self.assertIsNone(res.error)
        self.assertIn("Barolo Riserva", res.result)
        self.assertIn("94", res.result)

        listed = _run(
            tasting_main.list_tastings(
                tasting_main.ListTastingsRequest.model_validate({"uid": UID})
            )
        )
        self.assertIn("Barolo Riserva", listed.result)

        import re

        match = re.search(r"\(id: ([0-9a-f]{8})\)", listed.result)
        self.assertTrue(match)
        detail = _run(
            tasting_main.get_tasting(
                tasting_main.GetTastingRequest.model_validate(
                    {"uid": UID, "tasting_id": match.group(1)}
                )
            )
        )
        self.assertIsNone(detail.error)
        self.assertIn("Nebbiolo", detail.result)

    def test_list_tastings_empty(self):
        res = _run(
            tasting_main.list_tastings(
                tasting_main.ListTastingsRequest.model_validate({"uid": UID})
            )
        )
        self.assertEqual(res.result, "No tastings logged yet.")

    def test_list_tastings_filters_by_beverage(self):
        self._log(beverage_type="wine", name="Barolo")
        self._log(beverage_type="coffee", name="Ethiopian")
        res = _run(
            tasting_main.list_tastings(
                tasting_main.ListTastingsRequest.model_validate(
                    {"uid": UID, "beverage_type": "wine"}
                )
            )
        )
        self.assertIn("Barolo", res.result)
        self.assertNotIn("Ethiopian", res.result)

    def test_get_tasting_unknown_id(self):
        res = _run(
            tasting_main.get_tasting(
                tasting_main.GetTastingRequest.model_validate(
                    {"uid": UID, "tasting_id": "deadbeef"}
                )
            )
        )
        self.assertIsNotNone(res.error)

    def test_tasting_stats(self):
        self._log(beverage_type="wine", name="Barolo", score_100=94, verdict="buy")
        self._log(beverage_type="wine", name="Chianti", score_100=86, verdict="skip")
        res = _run(
            tasting_main.tasting_stats(
                tasting_main.StatsRequest.model_validate({"uid": UID})
            )
        )
        self.assertIn("2 total", res.result)
        self.assertIn("avg 90.0/100", res.result)
        self.assertIn("1 buy verdicts", res.result)

    def test_storage_is_per_user(self):
        self._log(name="Barolo")
        req = tasting_main.ListTastingsRequest.model_validate({"uid": "bob"})
        res = _run(tasting_main.list_tastings(req))
        self.assertEqual(res.result, "No tastings logged yet.")


class TestCandidatesFlow(_BaseTest):
    def test_candidates_listed_and_confirm_persists(self):
        hook = _run(
            tasting_main.tasting_candidate(_conversation(BAROLO_TRANSCRIPT), UID)
        )
        candidate_id = hook["candidate_id"]

        listed = _run(
            tasting_main.list_candidates(
                tasting_main.ListCandidatesRequest.model_validate({"uid": UID})
            )
        )
        self.assertIsNone(listed.error)
        self.assertIn(candidate_id, listed.result)

        confirm = _run(
            tasting_main.confirm_candidate(
                tasting_main.ConfirmCandidateRequest.model_validate(
                    {
                        "uid": UID,
                        "candidate_id": candidate_id,
                        "name": "Barolo Riserva 2019",
                        "producer": "G.D. Vajra",
                    }
                )
            )
        )
        self.assertIsNone(confirm.error)
        self.assertIn("Barolo Riserva 2019", confirm.result)

        # Candidate is consumed...
        listed_again = _run(
            tasting_main.list_candidates(
                tasting_main.ListCandidatesRequest.model_validate({"uid": UID})
            )
        )
        self.assertEqual(listed_again.result, "No candidates awaiting review.")

        # ...and the confirmed tasting persisted (not overwritten by a stale save).
        tastings = _run(
            tasting_main.list_tastings(
                tasting_main.ListTastingsRequest.model_validate({"uid": UID})
            )
        )
        self.assertIn("Barolo Riserva 2019", tastings.result)

        # Confirming twice fails.
        again = _run(
            tasting_main.confirm_candidate(
                tasting_main.ConfirmCandidateRequest.model_validate(
                    {"uid": UID, "candidate_id": candidate_id}
                )
            )
        )
        self.assertIsNotNone(again.error)

    def test_list_candidates_empty(self):
        res = _run(
            tasting_main.list_candidates(
                tasting_main.ListCandidatesRequest.model_validate({"uid": UID})
            )
        )
        self.assertEqual(res.result, "No candidates awaiting review.")

    def test_confirm_unknown_candidate(self):
        res = _run(
            tasting_main.confirm_candidate(
                tasting_main.ConfirmCandidateRequest.model_validate(
                    {"uid": UID, "candidate_id": "deadbeef"}
                )
            )
        )
        self.assertIsNotNone(res.error)


class TestManifestAndHealth(_BaseTest):
    def test_manifest_lists_six_tools(self):
        manifest = _run(tasting_main.omi_tools())
        tools = {t["name"] for t in manifest["tools"]}
        self.assertEqual(
            tools,
            {
                "log_tasting",
                "list_tastings",
                "list_candidates",
                "get_tasting",
                "tasting_stats",
                "confirm_candidate",
            },
        )

    def test_health(self):
        self.assertEqual(_run(tasting_main.health()), {"status": "ok"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
