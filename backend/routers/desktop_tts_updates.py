from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import hmac
import os
import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

from database import redis_db
from database._client import get_firestore_client
from utils.byok import get_byok_key
from utils.executors import critical_executor, db_executor, run_blocking
from utils.other.endpoints import get_current_user_uid
from utils.subscription import is_trial_paywalled

router = APIRouter()

_OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"
_OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
_MAX_TTS_CHARS = 4096
_TTS_BURST_PER_MINUTE = 20
_TTS_DAILY_CHARS = 50_000
_TTS_RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504, 529})
_OPENAI_VOICES = frozenset(
    {"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse", "marin", "cedar"}
)
_RELEASES_COLLECTION = "desktop_releases"


class TtsSynthesizeRequest(BaseModel):
    text: str
    voice_id: str
    instructions: str | None = None


class ReleaseInfo(BaseModel):
    version: str = Field(min_length=1)
    build_number: int = Field(ge=0)
    download_url: str = Field(min_length=1)
    manual_download_url: str | None = None
    ed_signature: str = Field(min_length=1)
    published_at: str
    changelog: list[str] = Field(default_factory=list)
    is_live: bool = False
    is_critical: bool = False
    channel: str | None = None


class CreateReleaseRequest(BaseModel):
    version: str = Field(min_length=1)
    build_number: int = Field(ge=0)
    download_url: str = Field(min_length=1)
    manual_download_url: str | None = None
    ed_signature: str = Field(min_length=1)
    changelog: list[str] = Field(default_factory=list)
    is_live: bool = False
    is_critical: bool = False
    channel: str | None = None


class PromoteReleaseRequest(BaseModel):
    doc_id: str = Field(min_length=1)


def _is_allowed_openai_voice(voice_id: str) -> bool:
    return voice_id in _OPENAI_VOICES


def _release_channel(release: ReleaseInfo) -> str:
    return release.channel or "staging"


def _manual_download_url(release: ReleaseInfo) -> str:
    if release.manual_download_url and release.manual_download_url.strip():
        return release.manual_download_url.strip()
    if release.download_url.endswith("/Omi.zip"):
        return f"{release.download_url[:-len('Omi.zip')]}Omi.dmg"
    return release.download_url


def _appcast_xml(releases: list[ReleaseInfo], platform: str) -> str:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">',
        "  <channel>",
        "    <title>Omi Desktop Updates</title>",
        "    <description>Omi AI Desktop Application</description>",
        "    <language>en</language>",
    ]
    seen_channels: set[str] = set()
    for release in releases:
        if not release.is_live or _release_channel(release) in seen_channels:
            continue
        seen_channels.add(_release_channel(release))
        changes = "<p>Bug fixes and improvements.</p>"
        if release.changelog:
            changes = "<ul>" + "".join(f"<li>{escape(change)}</li>" for change in release.changelog) + "</ul>"
        lines.extend(
            [
                "    <item>",
                f"      <title>Omi {escape(release.version)}</title>",
                f"      <sparkle:version>{release.build_number}</sparkle:version>",
                f"      <sparkle:shortVersionString>{escape(release.version)}</sparkle:shortVersionString>",
                f"      <description><![CDATA[{changes.replace(']]>', ']]]]><![CDATA[>')}]]></description>",
                f"      <pubDate>{escape(release.published_at)}</pubDate>",
                f'      <enclosure url="{escape(release.download_url, quote=True)}" type="application/octet-stream" sparkle:os="{escape(platform, quote=True)}" sparkle:edSignature="{escape(release.ed_signature, quote=True)}" />',
            ]
        )
        if release.channel != "stable":
            lines.append(f"      <sparkle:channel>{escape(_release_channel(release))}</sparkle:channel>")
        if release.is_critical:
            lines.append("      <sparkle:criticalUpdate />")
        lines.append("    </item>")
    lines.extend(["  </channel>", "</rss>", ""])
    return "\n".join(lines)


def _release_models() -> list[tuple[str, ReleaseInfo]]:
    snapshots = (
        get_firestore_client()
        .collection(_RELEASES_COLLECTION)
        .order_by("build_number", direction="DESCENDING")
        .stream()
    )
    releases: list[tuple[str, ReleaseInfo]] = []
    for snapshot in snapshots:
        try:
            releases.append((snapshot.id, ReleaseInfo.model_validate(snapshot.to_dict())))
        except Exception:
            continue
    return releases


def _create_release(request: CreateReleaseRequest) -> str:
    release = ReleaseInfo(**request.model_dump(), published_at=datetime.now(timezone.utc).isoformat())
    return get_firestore_client().collection(_RELEASES_COLLECTION).add(release.model_dump())[1].id


def _promote_release(doc_id: str) -> tuple[str, str]:
    ref = get_firestore_client().collection(_RELEASES_COLLECTION).document(doc_id)
    snapshot = ref.get()
    if not snapshot.exists:
        raise ValueError("release not found")
    release = ReleaseInfo.model_validate(snapshot.to_dict())
    old_channel = _release_channel(release)
    new_channel = {"staging": "beta", "beta": "stable"}.get(old_channel)
    if new_channel is None:
        raise ValueError("release is already stable")
    ref.update({"channel": new_channel})
    return old_channel, new_channel


def _release_authorized(secret: str | None) -> bool:
    expected = os.getenv("RELEASE_SECRET", "")
    return bool(expected) and bool(secret) and hmac.compare_digest(secret, expected)


async def _openai_tts(payload: dict[str, str], api_key: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        for attempt in range(3):
            try:
                response = await client.post(
                    _OPENAI_TTS_URL, headers={"Authorization": f"Bearer {api_key}"}, json=payload
                )
            except httpx.HTTPError as exc:
                if attempt == 2:
                    raise HTTPException(status_code=502, detail="OpenAI TTS request failed") from exc
            else:
                if response.status_code not in _TTS_RETRY_STATUSES or attempt == 2:
                    return response
        raise HTTPException(status_code=502, detail="OpenAI TTS request failed")


@router.post("/v1/tts/synthesize", responses={200: {"content": {"audio/mpeg": {}}}})
async def tts_synthesize(request: TtsSynthesizeRequest, uid: str = Depends(get_current_user_uid)):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    if len(text) > _MAX_TTS_CHARS:
        raise HTTPException(status_code=400, detail="text is too long")
    voice_id = request.voice_id.strip()
    if not _is_allowed_openai_voice(voice_id):
        raise HTTPException(status_code=400, detail="voice_id is not supported")
    if await run_blocking(db_executor, is_trial_paywalled, uid, "desktop"):
        raise HTTPException(status_code=403, detail="A paid subscription is required")
    api_key = get_byok_key("openai") or os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="OpenAI TTS is not configured")
    if not get_byok_key("openai"):
        status, _ = await run_blocking(
            critical_executor,
            redis_db.check_tts_rate_limit,
            uid,
            char_count=len(text),
            burst_limit=_TTS_BURST_PER_MINUTE,
            daily_char_limit=_TTS_DAILY_CHARS,
        )
        if status == -1:
            raise HTTPException(status_code=503, detail="TTS rate limiting is unavailable")
        if status == 1:
            raise HTTPException(status_code=429, detail="TTS burst rate limit exceeded")
        if status == 2:
            raise HTTPException(status_code=429, detail="TTS daily character limit exceeded")
    payload = {"model": _OPENAI_TTS_MODEL, "input": text, "voice": voice_id, "response_format": "mp3"}
    if request.instructions and request.instructions.strip():
        payload["instructions"] = request.instructions.strip()
    upstream = await _openai_tts(payload, api_key)
    if upstream.is_error:
        raise HTTPException(status_code=upstream.status_code, detail="OpenAI TTS request failed")
    return Response(content=upstream.content, media_type="audio/mpeg")


@router.get("/appcast.xml")
async def get_appcast(platform: str = Query(default="macos")):
    try:
        releases = [release for _, release in await run_blocking(db_executor, _release_models)]
    except Exception:
        return Response("Desktop update feed is temporarily unavailable", status_code=503, media_type="text/plain")
    return Response(
        _appcast_xml(releases, platform), media_type="application/xml", headers={"Cache-Control": "max-age=300"}
    )


@router.get("/updates/latest")
async def get_latest_version():
    try:
        releases = await run_blocking(db_executor, _release_models)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to fetch releases") from exc
    for _, release in releases:
        if release.is_live and release.channel == "stable":
            return {
                "version": release.version,
                "build_number": release.build_number,
                "download_url": release.download_url,
                "is_critical": release.is_critical,
            }
    raise HTTPException(status_code=404, detail="No live releases found")


@router.get("/download")
async def download_redirect():
    try:
        releases = await run_blocking(db_executor, _release_models)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to fetch releases") from exc
    for _, release in releases:
        if release.is_live and release.channel == "stable":
            return RedirectResponse(_manual_download_url(release), status_code=307)
    raise HTTPException(status_code=404, detail="No live releases found")


@router.post("/updates/releases", status_code=201)
async def create_release(request: CreateReleaseRequest, x_release_secret: str | None = Header(default=None)):
    if not _release_authorized(x_release_secret):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Release-Secret header")
    try:
        doc_id = await run_blocking(db_executor, _create_release, request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to create release") from exc
    return {"success": True, "doc_id": doc_id, "message": f"Release v{request.version} created successfully"}


@router.patch("/updates/releases/promote")
async def promote_release(request: PromoteReleaseRequest, x_release_secret: str | None = Header(default=None)):
    if not _release_authorized(x_release_secret):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Release-Secret header")
    try:
        old_channel, new_channel = await run_blocking(db_executor, _promote_release, request.doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Failed to promote: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Failed to promote release") from exc
    return {
        "success": True,
        "doc_id": request.doc_id,
        "old_channel": old_channel,
        "new_channel": new_channel,
        "message": f"Release promoted from {old_channel} to {new_channel}",
    }
