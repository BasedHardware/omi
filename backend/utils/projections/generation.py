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
from typing import Any, Mapping, cast

from utils.llm.gateway_client import generate_image_via_gateway
from utils.observability.fallback import record_fallback
from utils.projections.emotions import rate_emotions
from utils.projections.evidence import EvidencePacket
from utils.projections.image_prompt import build_image_prompt
from utils.projections.selector import MAX_PREVIOUS, SubjectSelection, select_subject
from utils.projections.sources import read_evidence, read_previous_projections
from utils.projections.storage import (
    local_projection_image_path,
    projection_image_path,
    upload_projection_image,
    uses_gcs,
)

logger = logging.getLogger(__name__)

PROJECTION_IMAGE_MODEL = 'gpt-image-1'
PROJECTION_IMAGE_SIZE = '1024x1536'
PROJECTION_IMAGE_QUALITY = 'medium'
PROJECTION_USAGE_FEATURE = 'projection_image'


def _public_base_url() -> str:
    return (os.getenv('BASE_API_URL') or 'http://127.0.0.1:8080').rstrip('/')


def _store_image(
    image_bytes: bytes,
    uid: str,
    projection_id: str,
    attempt_token: str | None = None,
) -> str:
    """Persist an owner-scoped private image and return its storage reference.

    Production stores in private GCS without object ACL changes. Local development stores
    under a hashed owner directory. Neither storage path is itself a delivery authority:
    the authenticated image route verifies the projection belongs to the requesting uid.
    """
    if uses_gcs():
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as handle:
            handle.write(image_bytes)
            temp_path = handle.name
        try:
            return upload_projection_image(temp_path, uid, projection_id, attempt_token)
        finally:
            os.unlink(temp_path)

    record_fallback(
        component='projections',
        from_mode='gcs',
        to_mode='local_disk',
        reason='config_incomplete',
        outcome='degraded',
        log=logger,
    )
    path = local_projection_image_path(uid, projection_id, attempt_token)
    path.write_bytes(image_bytes)
    path.chmod(0o600)
    return projection_image_path(uid, projection_id, attempt_token)


def generate_projection(
    uid: str,
    *,
    projection_id: str | None = None,
    cadence_key: str | None = None,
    attempt_token: str | None = None,
) -> dict[str, Any]:
    """Generate, store and return one projection document for `uid`.

    Raises `NoProjectionSubject` when there is nothing to project from, or when nothing the
    selector ranked was grounded in the evidence. The caller is responsible for persisting
    the returned document.
    """
    projection_id = projection_id or str(uuid.uuid4())

    packet = read_evidence(uid)
    previous = read_previous_projections(uid, MAX_PREVIOUS)
    selection = select_subject(packet, previous=previous)
    subject = selection.subject

    # A dedicated pass, deliberately not another field on the selection call: making a model
    # rate and predict in one call measurably degrades the ratings.
    emotions = rate_emotions(subject.subject, subject.evidence, packet.as_prompt_text())

    image_prompt = build_image_prompt(subject, emotions)
    image_path = _store_image(_generate_image(image_prompt), uid, projection_id, attempt_token)
    why_this = _why_this_receipt(packet, selection)
    logger.info(
        'generated projection uid=%s projection_id=%s stage=%s fell_through=%s',
        uid,
        projection_id,
        subject.stage.value,
        selection.metadata['fell_through'],
    )

    projection = {
        'id': projection_id,
        'created_at': datetime.now(timezone.utc),
        'imperative': subject.imperative,
        'image_url': f'{_public_base_url()}/v1/projection-images/{projection_id}.png',
        'image_path': image_path,
        'subject': subject.subject,
        'stage': subject.stage.value,
        'projection': subject.projection,
        'setting': subject.setting,
        'tone': subject.tone,
        'emotions': emotions.as_metadata(),
        'evidence': list(subject.evidence),
        'why_this': why_this,
        'selection': selection.metadata,
        'generation': {
            'model': PROJECTION_IMAGE_MODEL,
            'size': PROJECTION_IMAGE_SIZE,
            'quality': PROJECTION_IMAGE_QUALITY,
            'prompt': image_prompt,
        },
    }
    if cadence_key:
        projection['cadence_key'] = cadence_key
    return projection


def _why_this_receipt(packet: EvidencePacket, selection: SubjectSelection) -> dict[str, Any]:
    """Build a compact owner-visible receipt without exposing prompt or overview prose."""
    selection_rank = int(selection.metadata.get('fell_through') or 0) + 1
    uncertainty: list[str] = []
    if packet.tier.value == 'thin':
        uncertainty.append('No recent conversation overview was available; this used open action items.')
    if selection_rank > 1:
        uncertainty.append(
            f'{selection_rank - 1} higher-ranked candidate'
            f'{"s" if selection_rank > 2 else ""} did not pass grounding checks.'
        )
    if not uncertainty:
        uncertainty.append('Selected from the highest-ranked grounded thread in the available window.')
    return {
        'evidence': packet.receipts_for(selection.subject.evidence),
        'evidence_tier': packet.tier.value,
        'selection_rank': selection_rank,
        'uncertainty': uncertainty,
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
