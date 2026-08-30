from datetime import datetime, timezone
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image

from models.frame_request import FrameRequest, FrameRequestCleanupState, FrameRequestPromotion, FrameRequestState
from routers import frame_requests
from utils.jit_rollout import JITDecisionStage, TriState
from utils.retrieval import frame_request_authority


async def _allow(_uid: str, _generation: int, **_kwargs) -> None:
    return None


def _request(state: FrameRequestState) -> FrameRequest:
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return FrameRequest(
        request_id="frame-1",
        uid="user-1",
        device_id="desktop-1",
        account_generation=3,
        dedupe_key="opaque",
        conversation_id="conversation-1",
        screenshot_id="42",
        state=state,
        created_at=now,
        expires_at=now if state == FrameRequestState.attached else now.replace(day=25),
        storage_id="storage-1",
        byte_count=1024,
        content_type="image/jpeg",
        cleanup_state=(
            FrameRequestCleanupState.permanent
            if state == FrameRequestState.attached
            else FrameRequestCleanupState.pending
        ),
    )


@pytest.mark.asyncio
async def test_attached_retry_is_idempotent_and_never_cleans_permanent_evidence(monkeypatch):
    request = _request(FrameRequestState.attached)
    acknowledged = []
    monkeypatch.setattr(frame_requests, "_authorize", _allow)
    monkeypatch.setattr(frame_requests, "get_frame_request", lambda uid, request_id: request)
    monkeypatch.setattr(
        frame_requests,
        "acknowledge_frame_storage_cleanup",
        lambda uid, storage_id: acknowledged.append((uid, storage_id)),
    )
    monkeypatch.setattr(
        frame_requests,
        "delete_frame_request_pixels",
        lambda *args: pytest.fail("permanent pixels must not be deleted on retry"),
    )

    result = await frame_requests.promote_frame_request(
        "frame-1",
        FrameRequestPromotion(device_id="desktop-1", account_generation=3, conversation_id="conversation-1"),
        uid="user-1",
    )

    assert result.request.state == FrameRequestState.attached
    assert acknowledged == [("user-1", "storage-1")]


def test_image_decoder_accepts_only_bounded_jpeg_png_and_webp(monkeypatch):
    for image_format, content_type in (("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")):
        payload = BytesIO()
        Image.new("RGB", (2, 2), color="white").save(payload, format=image_format)
        assert frame_requests._validated_image_content_type(payload.getvalue()) == content_type

    with pytest.raises(HTTPException) as invalid:
        frame_requests._validated_image_content_type(b"not-an-image")
    assert invalid.value.status_code == 415

    class OversizedImage:
        format = "PNG"
        size = (5001, 5001)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def verify(self):
            return None

    monkeypatch.setattr(frame_requests.Image, "open", lambda *_args: OversizedImage())
    with pytest.raises(HTTPException) as oversized:
        frame_requests._validated_image_content_type(b"header")
    assert oversized.value.status_code == 413


@pytest.mark.asyncio
async def test_ambiguous_state_commit_leaves_object_retryable(monkeypatch):
    request = _request(FrameRequestState.uploaded)
    monkeypatch.setattr(frame_requests, "_authorize", _allow)
    monkeypatch.setattr(frame_requests, "get_frame_request", lambda uid, request_id: request)
    monkeypatch.setattr(
        frame_requests,
        "attach_frame_request_to_conversation",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("commit outcome unknown")),
    )
    monkeypatch.setattr(frame_requests, "reserve_frame_promotion_copy", lambda *args: None)
    monkeypatch.setattr(frame_requests, "reserve_frame_storage_cleanup", lambda *args: None)
    monkeypatch.setattr(frame_requests, "copy_frame_request_pixels_to_permanent", lambda *args: None)
    monkeypatch.setattr(
        frame_requests,
        "delete_frame_request_pixels",
        lambda *args: pytest.fail("ambiguous commit must not delete the object"),
    )

    with pytest.raises(RuntimeError, match="commit outcome unknown"):
        await frame_requests.promote_frame_request(
            "frame-1",
            FrameRequestPromotion(device_id="desktop-1", account_generation=3, conversation_id="conversation-1"),
            uid="user-1",
        )


@pytest.mark.asyncio
async def test_ambiguous_upload_commit_reconciles_without_deleting_object(monkeypatch):
    request = _request(FrameRequestState.uploaded)
    uploaded_storage_id = ""
    monkeypatch.setattr(frame_requests, "_authorize", _allow)
    monkeypatch.setattr(frame_requests, "upload_frame_request_pixels", lambda *args: None)

    async def run_blocking(_executor, function, *args, **kwargs):
        if function is frame_requests.upload_frame_request_pixels:
            nonlocal uploaded_storage_id
            uploaded_storage_id = args[1]
            return None
        if function is frame_requests.transition_frame_request:
            raise RuntimeError("commit outcome unknown")
        if function is frame_requests.reconcile_ambiguous_frame_upload:
            return request.model_copy(update={"storage_id": uploaded_storage_id})
        raise AssertionError(function)

    monkeypatch.setattr(frame_requests, "run_blocking", run_blocking)
    monkeypatch.setattr(
        frame_requests,
        "delete_frame_request_pixels",
        lambda *args: pytest.fail("ambiguous upload must not delete an object"),
    )

    image = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(image, format="JPEG")
    image.seek(0)
    result = await frame_requests.upload_frame_request(
        "frame-1",
        device_id="desktop-1",
        account_generation=3,
        file=UploadFile(filename="frame.jpg", file=image, headers={"content-type": "image/jpeg"}),
        uid="user-1",
    )
    assert result.request.state == FrameRequestState.uploaded


@pytest.mark.asyncio
async def test_upload_rechecks_authority_after_canonicalization_before_gcs(monkeypatch):
    authority_checks = []
    canonicalized = False

    async def authorize(_uid, _generation, **kwargs):
        authority_checks.append((canonicalized, kwargs))
        if canonicalized:
            raise HTTPException(status_code=503, detail="frame_requests_unavailable")

    def canonicalize(payload):
        nonlocal canonicalized
        canonicalized = True
        return payload

    monkeypatch.setattr(frame_requests, "_authorize", authorize)
    monkeypatch.setattr(frame_requests, "_canonicalize_frame_image", canonicalize)
    monkeypatch.setattr(
        frame_requests,
        "upload_frame_request_pixels",
        lambda *_args, **_kwargs: pytest.fail("revoked upload must not reach GCS"),
    )

    image = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(image, format="JPEG")
    image.seek(0)
    with pytest.raises(HTTPException) as error:
        await frame_requests.upload_frame_request(
            "frame-1",
            device_id="desktop-1",
            account_generation=3,
            file=UploadFile(filename="frame.jpg", file=image, headers={"content-type": "image/jpeg"}),
            uid="user-1",
        )

    assert error.value.status_code == 503
    assert authority_checks == [
        (False, {"mutation": True}),
        (True, {"mutation": True}),
    ]


@pytest.mark.asyncio
async def test_frame_authority_reuses_shared_rollout_and_generation_fence(monkeypatch):
    calls = []

    async def resolve(uid, *, stage, force_refresh):
        calls.append((uid, stage, force_refresh))
        return type("Rollout", (), {"permits_work": True, "kill_switch": TriState.DISABLED})()

    async def run_blocking(_executor, function, uid):
        assert function is frame_request_authority._account_generation
        assert uid == "user-1"
        return 9

    monkeypatch.setattr(frame_request_authority, "resolve_jit_rollout", resolve)
    monkeypatch.setattr(frame_request_authority, "run_blocking", run_blocking)

    enabled = await frame_request_authority.resolve_frame_request_authority(
        "user-1", stage=JITDecisionStage.PAID_BOUNDARY, force_refresh=True
    )

    assert enabled.enabled is True and enabled.account_generation == 9
    assert calls == [("user-1", JITDecisionStage.PAID_BOUNDARY, True)]


@pytest.mark.asyncio
async def test_frame_authority_fails_closed_before_generation_read(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return type("Rollout", (), {"permits_work": False, "kill_switch": TriState.ENABLED})()

    monkeypatch.setattr(frame_request_authority, "resolve_jit_rollout", resolve)
    monkeypatch.setattr(
        frame_request_authority,
        "run_blocking",
        lambda *_args, **_kwargs: pytest.fail("disabled rollout must not read account generation"),
    )

    killed = await frame_request_authority.resolve_frame_request_authority(
        "user-1", stage=JITDecisionStage.INGRESS, force_refresh=True
    )

    assert killed.enabled is False and killed.kill_switch is True
