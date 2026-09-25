"""Per-candidate adjudication pipeline (contract §4).

canonicalize -> judge -> (if approved_clean) mint approval -> write -> derive
palette ground.

This module owns candidate-level fail-closed handling: canonicalization
failures and judge failures both produce `written=None` (nothing stored, no
approval minted) without raising — one bad candidate in an up-to-8-candidate
batch must not sink the rest. Writer failures DO raise, because by the time
the writer is called the candidate has already been judged approved_clean by
this same process moments earlier; a failure there is an infrastructure
problem (Redis down, GCS unavailable), not a fresh quality judgement about
the candidate, so the router surfaces it as 503 rather than silently
dropping the frame.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

from models.screen_frame import ScreenFrameCandidateIn
from utils.screen_frames import palette
from utils.screen_frames.approval import build_approval_claims, mint_approval
from utils.screen_frames.canonicalize import ScreenFrameCanonicalizationError, canonicalize_candidate
from utils.screen_frames.enforcement import NewPersistedFrame
from utils.screen_frames.judge import ScreenFrameJudgeError, judge_frame
from utils.screen_frames.policy import ScreenFramePurposePolicy
from utils.screen_frames.writer import write_screen_frame

logger = logging.getLogger(__name__)


class ScreenFrameDigestMismatch(Exception):
    """The client-declared sha256_base64 does not match the decoded bytes,
    or the base64 payload itself is undecodable (contract §4 step 1 — a
    transport check only, confers no authority). The router treats this as
    a request-level 400.
    """


@dataclass(frozen=True)
class CandidateOutcome:
    client_frame_id: str
    written: Optional[NewPersistedFrame]


def decode_and_verify_transport_digest(candidate: ScreenFrameCandidateIn) -> bytes:
    """Step 1 of contract §4. Raises ScreenFrameDigestMismatch on any
    mismatch or undecodable input."""
    try:
        raw_bytes = base64.b64decode(candidate.bytes_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ScreenFrameDigestMismatch("undecodable_bytes_base64") from error

    try:
        declared_digest = base64.b64decode(candidate.sha256_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ScreenFrameDigestMismatch("undecodable_sha256_base64") from error

    if len(declared_digest) != hashlib.sha256().digest_size:
        raise ScreenFrameDigestMismatch("wrong_digest_length")

    actual_digest = hashlib.sha256(raw_bytes).digest()
    if actual_digest != declared_digest:
        raise ScreenFrameDigestMismatch("digest_mismatch")

    return raw_bytes


def adjudicate_candidate(
    *,
    uid: str,
    purpose: str,
    subject_id: str,
    policy: ScreenFramePurposePolicy,
    candidate: ScreenFrameCandidateIn,
    raw_bytes: bytes,
) -> CandidateOutcome:
    try:
        canonical = canonicalize_candidate(raw_bytes)
    except ScreenFrameCanonicalizationError as error:
        logger.info(
            "screen_frame candidate failed canonicalization uid=%s client_frame_id=%s reason=%s",
            uid,
            candidate.client_frame_id,
            error.reason,
        )
        return CandidateOutcome(client_frame_id=candidate.client_frame_id, written=None)

    try:
        judgement = judge_frame(uid, canonical.jpeg_bytes)
    except ScreenFrameJudgeError as error:
        logger.info(
            "screen_frame candidate failed judging uid=%s client_frame_id=%s error=%s",
            uid,
            candidate.client_frame_id,
            error,
        )
        return CandidateOutcome(client_frame_id=candidate.client_frame_id, written=None)

    if judgement.outcome != "approved_clean":
        return CandidateOutcome(client_frame_id=candidate.client_frame_id, written=None)

    # Extracted once, here, at approval time — never recomputed per read.
    ground = palette.compute_ground(canonical.jpeg_bytes)

    claims = build_approval_claims(
        uid=uid,
        purpose=purpose,
        subject_id=subject_id,
        canonical_sha256=canonical.sha256_hex,
        model=policy.model,
        policy_version=policy.policy_version,
        prompt_version=policy.prompt_version,
        retention=policy.retention.value,
        judgement=judgement,
    )
    token = mint_approval(claims)

    # write_screen_frame independently re-verifies the digest and expiry —
    # not redundant: it is the writer refusing to trust anything this
    # process claims about a token without checking it itself.
    written = write_screen_frame(
        token, jpeg_bytes=canonical.jpeg_bytes, thumbnail_jpeg_bytes=canonical.thumbnail_jpeg_bytes
    )

    return CandidateOutcome(
        client_frame_id=candidate.client_frame_id,
        written=NewPersistedFrame(
            frame_id=written.frame_id,
            captured_at=candidate.captured_at,
            caption=judgement.caption,
            labels=list(judgement.labels),
            source_badge=judgement.source_badge,
            banner_suitability=judgement.banner_suitability,
            width=canonical.width,
            height=canonical.height,
            canonical_sha256=canonical.sha256_hex,
            ground=ground,
        ),
    )
