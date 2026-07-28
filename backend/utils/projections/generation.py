"""Generation of projections — a generated image carrying one future-tense imperative.

Composes the two halves. `sources` and `evidence` gather what the projection is selected
from, `selector` decides what it is about, `image_prompt` renders it. This module owns the
image call, storage, and the shape of the persisted document.

Every generation records what produced it — the signals that selected the subject, the model,
the prompts, the timestamps, and whether the top-ranked candidate survived the grounding gate.
That is cheap here and unrecoverable afterwards.
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
from utils.projections.image_prompt import build_image_prompt
from utils.projections.selector import MAX_PREVIOUS, select_subject
from utils.projections.sources import read_evidence, read_previous_projections

logger = logging.getLogger(__name__)

PROJECTION_IMAGE_MODEL = 'gpt-image-1'
PROJECTION_IMAGE_SIZE = '1024x1536'
PROJECTION_IMAGE_QUALITY = 'medium'
PROJECTION_USAGE_FEATURE = 'projection_image'


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

    Raises `NoProjectionSubject` when there is nothing to project from, or when nothing the
    selector ranked was grounded in the evidence. The caller is responsible for persisting
    the returned document.
    """
    projection_id = str(uuid.uuid4())

    packet = read_evidence(uid)
    previous = read_previous_projections(uid, MAX_PREVIOUS)
    selection = select_subject(packet, previous=previous)
    subject = selection.subject

    image_prompt = build_image_prompt(subject)
    image_url = _store_image(_generate_image(image_prompt), projection_id)
    logger.info(
        'generated projection uid=%s projection_id=%s stage=%s fell_through=%s',
        uid,
        projection_id,
        subject.stage.value,
        selection.metadata['fell_through'],
    )

    return {
        'id': projection_id,
        'created_at': datetime.now(timezone.utc),
        'imperative': subject.imperative,
        'image_url': image_url,
        'subject': subject.subject,
        'stage': subject.stage.value,
        'projection': subject.projection,
        'evidence': list(subject.evidence),
        'selection': selection.metadata,
        'generation': {
            'model': PROJECTION_IMAGE_MODEL,
            'size': PROJECTION_IMAGE_SIZE,
            'quality': PROJECTION_IMAGE_QUALITY,
            'prompt': image_prompt,
        },
    }


def _generate_image(prompt: str) -> bytes:
    response = cast(
        Mapping[str, Any],
        generate_image_via_gateway(
            model=PROJECTION_IMAGE_MODEL,
            prompt=prompt,
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
    return base64.b64decode(encoded)
