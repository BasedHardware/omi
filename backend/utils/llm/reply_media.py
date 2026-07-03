"""
Resolve the links and images shared in a chat into text the reply drafter can
actually understand — so it grasps what a shared URL is about and what an image
shows, instead of seeing a bare URL or a 📷 marker.

Kept separate from reply_draft.py on purpose: this pulls the web-fetch tools and
the vision model (heavy import chains), while reply_draft stays lightweight. The
routers await build_media_context() and pass the resulting string into the sync
draft_reply(..., media_context=...).
"""

import asyncio
import logging
import re
from typing import List

from utils.llm.openglass import describe_image
from utils.retrieval.tools.web_tools import fetch_url_summary

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r'https?://[^\s<>"\')\]]+')
MAX_LINKS = 3
MAX_IMAGES = 2
# Hard budgets so a slow link or a vision call the provider can't handle never
# hangs the draft request past the client timeout — we just draft without it.
LINK_BUDGET_SECONDS = 8
IMAGE_BUDGET_SECONDS = 12


async def build_media_context(uid: str, thread: List[dict]) -> str:
    """Async (network + vision). Degrades gracefully — anything that fails is skipped."""
    bits: List[str] = []

    # Links — most recent first, deduped, capped. SSRF-protected by fetch_url_tool.
    urls: List[str] = []
    for m in reversed(thread or []):
        for u in _URL_RE.findall(m.get('text') or ''):
            if u not in urls:
                urls.append(u)
        if len(urls) >= MAX_LINKS:
            break
    urls = urls[:MAX_LINKS]
    if urls:
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[fetch_url_summary(u) for u in urls], return_exceptions=True),
                timeout=LINK_BUDGET_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"reply_media: link fetch timed out/failed uid={uid}: {e}")
            results = []
        lines = []
        for u, r in zip(urls, results):
            if not isinstance(r, str) or not r.strip():
                continue
            # fetch_url_summary leads with og:title/og:description (the title +
            # caption of reels/videos too), then a little body text.
            summary = r.strip().replace('\n', ' ')
            lines.append(f"- {u}\n  {summary}")
        if lines:
            bits.append(
                "LINKS SHARED IN THIS CHAT (resolved — what each link/reel/video actually is, from its "
                "title & caption):\n" + "\n".join(lines)
            )

    # Images — describe the most recent ones the client attached (base64 JPEG).
    images: List[str] = []
    for m in reversed(thread or []):
        b64 = m.get('image_b64')
        if b64:
            images.append(b64)
        if len(images) >= MAX_IMAGES:
            break
    if images:
        try:
            descs = await asyncio.wait_for(
                asyncio.gather(*[describe_image(uid, b) for b in images], return_exceptions=True),
                timeout=IMAGE_BUDGET_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"reply_media: image description timed out/failed uid={uid}: {e}")
            descs = []
        lines = [f"- {d.strip()}" for d in descs if isinstance(d, str) and d.strip()]
        if lines:
            bits.append("IMAGES SHARED IN THIS CHAT (what they show):\n" + "\n".join(lines))

    return "\n\n".join(bits)
