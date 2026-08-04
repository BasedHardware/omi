"""Public Sparkle feeds for registered micro-app identities."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from utils import micro_app_updates

router = APIRouter()


@router.get("/v2/micro-apps/{app_id}/appcast.xml")
async def get_micro_app_appcast_xml(
    app_id: str,
    channel: Literal["stable", "beta"] = Query(default="stable"),
) -> Response:
    """Return a public, identity-scoped Sparkle 2 appcast.

    A registered app with no eligible signed release returns a cacheable empty
    feed.  Unknown IDs fail closed, and an upstream provider failure is exposed
    as temporary unavailability so clients do not cache it as "no update".
    """
    try:
        xml_content = await micro_app_updates.build_micro_app_appcast(app_id, channel)
    except micro_app_updates.UnknownMicroAppError as exc:
        raise HTTPException(status_code=404, detail="Unknown micro-app") from exc
    except micro_app_updates.MicroAppReleaseProviderError as exc:
        raise HTTPException(status_code=503, detail="Micro-app release provider unavailable") from exc

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": micro_app_updates.MICRO_APP_FEED_CACHE_CONTROL},
    )
