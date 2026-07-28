"""Generation of projections — a generated image carrying one future-tense imperative.

This is the spike surface for the non-chat-box output: hardcoded content in, a real
generated image and one line of text out, persisted and served over the authenticated API.
Subject selection, prompt quality and visual style are deliberately not here yet.
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast

from utils.llm.gateway_client import generate_image_via_gateway
from utils.observability.fallback import record_fallback
from utils.other import storage

logger = logging.getLogger(__name__)

PROJECTION_IMAGE_MODEL = 'gpt-image-1'
PROJECTION_IMAGE_SIZE = '1024x1536'
PROJECTION_IMAGE_QUALITY = 'medium'
PROJECTION_USAGE_FEATURE = 'projection_image'

# Hardcoded until subject selection exists. The shape is the point, not the content.
HARDCODED_IMPERATIVE = 'Send the message you have been drafting in your head all week.'
HARDCODED_IMAGE_PROMPT = (
    'A quiet photographic scene of a phone face-up on a windowsill in late afternoon light, '
    'one unsent message glowing on the screen, shallow depth of field, muted natural colour.'
)


def _local_image_root() -> Path:
    root = Path(os.getenv('PROJECTION_LOCAL_IMAGE_DIR') or Path(tempfile.gettempdir()) / 'omi-projection-images')
    root.mkdir(parents=True, exist_ok=True)
    return root


def local_projection_image_path(projection_id: str) -> Path:
    """Path of a locally stored projection image, used when no GCS bucket is configured."""
    return _local_image_root() / f'{projection_id}.png'


def _public_base_url() -> str:
    return (os.getenv('BASE_API_URL') or 'http://127.0.0.1:8080').rstrip('/')


def _store_image(image_bytes: bytes, projection_id: str) -> str:
    """Persist the image and return the URL the client will load it from.

    Production stores in GCS and returns the public object URL. When no bucket is
    configured — the local development case, which has no GCS credentials — the image is
    written to disk and served by this backend at an equivalently unguessable URL.
    """
    if storage.projection_images_bucket:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as handle:
            handle.write(image_bytes)
            temp_path = handle.name
        try:
            return storage.upload_projection_image(temp_path, projection_id)
        finally:
            os.unlink(temp_path)

    record_fallback(
        component='projections',
        from_mode='gcs',
        to_mode='local_disk',
        reason='missing_config',
        outcome='degraded',
        log=logger,
    )
    local_projection_image_path(projection_id).write_bytes(image_bytes)
    return f'{_public_base_url()}/v1/projection-images/{projection_id}.png'


def generate_projection(uid: str) -> dict[str, Any]:
    """Generate, store and return one projection document for `uid`.

    The caller is responsible for persisting the returned document.
    """
    projection_id = str(uuid.uuid4())

    response = cast(
        Mapping[str, Any],
        generate_image_via_gateway(
            model=PROJECTION_IMAGE_MODEL,
            prompt=HARDCODED_IMAGE_PROMPT,
            size=PROJECTION_IMAGE_SIZE,
            quality=PROJECTION_IMAGE_QUALITY,
            n=1,
            feature=PROJECTION_USAGE_FEATURE,
        ),
    )
    data = response.get('data')
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise ValueError('gateway image response carried no image data')
    encoded = data[0].get('b64_json')
    if not isinstance(encoded, str) or not encoded:
        raise ValueError('gateway image response carried no b64_json payload')

    image_url = _store_image(base64.b64decode(encoded), projection_id)
    logger.info('generated projection uid=%s projection_id=%s', uid, projection_id)

    return {
        'id': projection_id,
        'created_at': datetime.now(timezone.utc),
        'imperative': HARDCODED_IMPERATIVE,
        'image_url': image_url,
        'generation': {
            'model': PROJECTION_IMAGE_MODEL,
            'size': PROJECTION_IMAGE_SIZE,
            'quality': PROJECTION_IMAGE_QUALITY,
            'prompt': HARDCODED_IMAGE_PROMPT,
        },
    }
