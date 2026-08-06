"""One drawn image of something that actually happened.

The image is illustration, never evidence. It is generated from a moment taken
out of the day's own record, and the moment is printed as the caption so the
reader can see what it is drawing. An image with no moment behind it is
decoration, and decoration presented as memory is a fabrication — so a photo
without a grounded moment is not printed at all.

No faces and no text: image models garble type, and a rendered likeness of a
real person the reader knows lands badly and is not something we can get right.
"""

import base64
import logging
from typing import Any, cast

from models.paper import Photo
from utils.llm.gateway_client import generate_image_via_gateway
from utils.log_sanitizer import sanitize

from .editorial import ask_model, clip
from .context import DayContext, record_lines

logger = logging.getLogger(__name__)

IMAGE_MODEL = 'gpt-image-1'
IMAGE_SIZE = '1024x1024'
IMAGE_QUALITY = 'medium'

_STYLE_SUFFIX = (
    'Warm editorial illustration, soft muted palette, loose ink linework on paper. '
    'No text, no words, no letters, no numbers. No faces, no recognisable people.'
)

_MOMENT_PROMPT = """Pick one small, warm, human moment from this person's day and describe it \
as a picture.

THE RECORD ({day}):
{record}

Pick something ordinary and good: a place they were, a thing they made, a walk, a meal, a \
late night working. Not a task list, not a metric, not a screenshot.

HARD RULE: the moment must be in the record above. If the record has no such moment, return \
empty strings. Do not invent a nice day.

Return only JSON, no fences:
{{
  "moment": "<the thing from the record this depicts, one short phrase>",
  "caption": "<one plain sentence, present tense>",
  "scene": "<a visual description for an illustrator. No people's faces, no text in the image.>"
}}"""


def make_photo(uid: str, context: DayContext) -> Photo | None:
    """Draw one moment from the day, or return None if there wasn't one."""
    lines = record_lines(context)
    if not lines:
        return None

    payload = ask_model(
        uid,
        _MOMENT_PROMPT.format(day=context.day.isoformat(), record='\n'.join(lines)),
        'omi-paper-photo',
    )

    moment = clip(payload.get('moment'), 160)
    scene = clip(payload.get('scene'), 600)
    if not moment or not scene:
        logger.info('paper: no groundable moment for the photo, omitting')
        return None

    prompt = f'{scene} {_STYLE_SUFFIX}'
    try:
        response = generate_image_via_gateway(
            model=IMAGE_MODEL,
            prompt=prompt,
            size=IMAGE_SIZE,
            quality=IMAGE_QUALITY,
            n=1,
            response_format='b64_json',
        )
        data = cast(list[dict[str, Any]], response.get('data') or [])
        image_b64 = str(data[0].get('b64_json') or '') if data else ''
        # Reject anything that is not decodable rather than shipping a broken tag.
        if image_b64:
            base64.b64decode(image_b64, validate=True)
    except Exception as e:  # noqa: BLE001 — the photo is the most optional thing on the page.
        logger.warning('paper: image generation failed: %s', sanitize(str(e)))
        return None

    if not image_b64:
        return None

    return Photo(
        moment=moment,
        caption=clip(payload.get('caption'), 200),
        prompt=prompt,
        image_b64=image_b64,
    )
