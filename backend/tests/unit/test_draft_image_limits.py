import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.draft_common import MAX_DRAFT_IMAGES, MAX_IMAGE_B64_CHARS  # noqa: E402
from models.imessage import IMessageDraftMessage, IMessageDraftRequest  # noqa: E402
from models.telegram import TelegramDraftMessage, TelegramDraftRequest  # noqa: E402
from models.whatsapp import WhatsAppDraftMessage, WhatsAppDraftRequest  # noqa: E402


def _img(n):
    return "A" * n


def test_within_limits_is_accepted():
    req = IMessageDraftRequest(
        person="+1",
        thread=[IMessageDraftMessage(text="hi", image_b64=_img(1000)) for _ in range(MAX_DRAFT_IMAGES)],
    )
    assert len(req.thread) == MAX_DRAFT_IMAGES


def test_too_many_images_rejected():
    with pytest.raises(ValidationError):
        IMessageDraftRequest(
            person="+1",
            thread=[IMessageDraftMessage(text="hi", image_b64=_img(10)) for _ in range(MAX_DRAFT_IMAGES + 1)],
        )


def test_oversized_image_rejected():
    with pytest.raises(ValidationError):
        IMessageDraftRequest(
            person="+1",
            thread=[IMessageDraftMessage(text="hi", image_b64=_img(MAX_IMAGE_B64_CHARS + 1))],
        )


def test_no_images_ok():
    req = IMessageDraftRequest(person="+1", thread=[IMessageDraftMessage(text="hi")])
    assert req.thread[0].image_b64 is None


def test_limits_enforced_for_telegram_and_whatsapp():
    # Same shared validator guards all three connectors.
    with pytest.raises(ValidationError):
        TelegramDraftRequest(
            person="tg:1",
            thread=[TelegramDraftMessage(text="hi", image_b64=_img(MAX_IMAGE_B64_CHARS + 1))],
        )
    with pytest.raises(ValidationError):
        WhatsAppDraftRequest(
            person="+1",
            thread=[WhatsAppDraftMessage(text="hi", image_b64=_img(10)) for _ in range(MAX_DRAFT_IMAGES + 1)],
        )


def test_aggregate_image_size_rejected():
    from models.draft_common import MAX_TOTAL_IMAGE_B64_CHARS

    # Each image is under the per-image cap and the count is within MAX_DRAFT_IMAGES,
    # but together they exceed the aggregate cap.
    per = MAX_IMAGE_B64_CHARS // 2  # under per-image cap
    count = (MAX_TOTAL_IMAGE_B64_CHARS // per) + 2  # pushes the sum over the aggregate cap
    assert count <= MAX_DRAFT_IMAGES  # keep count within the per-count limit
    with pytest.raises(ValidationError):
        IMessageDraftRequest(
            person="+1",
            thread=[IMessageDraftMessage(text="hi", image_b64=_img(per)) for _ in range(count)],
        )
