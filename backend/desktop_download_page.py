"""HTML for the desktop download landing page.

Split out of ``routers/updates.py``: the appcast/update-routing logic and the
marketing-facing download page change for unrelated reasons and at unrelated
times, and keeping both in one module pushed it past the product file
line-count ratchet.
"""

from datetime import datetime, timezone
from typing import Optional

LANDING_ASSET_BASE = "https://storage.googleapis.com/omi_macos_updates/landing"

_CURSOR_SVG = (
    '<svg class="cursor" viewBox="0 0 12 18" width="12" height="18" aria-hidden="true">'
    '<path d="M1 1l9.2 8.4-4.1.3 2.4 5-1.9.9-2.4-5-3.2 2.6z" fill="#fff" stroke="#000"'
    ' stroke-width="1" stroke-linejoin="round"/></svg>'
)


def install_steps_html(platform: str) -> str:
    """Three illustrated install steps, drawn from real app chrome rather than a text list."""
    if platform == "windows":
        panels = [
            (
                '<div class="win-file"><div class="win-file-glyph">EXE</div>'
                '<div class="win-file-name">omi-setup.exe</div></div>' + _CURSOR_SVG,
                'Open <b>omi-setup.exe</b> from<br>your <b>Downloads</b> folder',
            ),
            (
                '<div class="win-dialog"><div class="win-dialog-title">Windows protected your PC</div>'
                '<div class="win-dialog-link">More info</div>'
                '<div class="win-dialog-run">Run anyway</div></div>',
                'If SmartScreen appears, click<br><b>More info</b> &rarr; <b>Run anyway</b>',
            ),
            (
                '<div class="app-row is-omi"><img src="' + LANDING_ASSET_BASE + '/omi-icon.png"'
                ' alt="" width="26" height="26"><span>Omi</span></div>'
                '<div class="app-row"><span class="app-dot"></span><span>Start menu</span></div>',
                'Launch <b>Omi</b> and finish<br>the setup wizard',
            ),
        ]
    else:
        panels = [
            (
                '<div class="finder">'
                '<div class="finder-bar"><i></i><i></i><i></i><span>Downloads</span></div>'
                '<div class="app-row is-omi"><span class="dmg-glyph"></span><span>omi.dmg</span>'
                + _CURSOR_SVG
                + '</div>'
                '<div class="app-row"><span class="app-dot"></span><span>Screenshot.png</span></div>'
                '</div>',
                'Open <b>omi.dmg</b> from<br>your <b>Downloads</b> folder',
            ),
            (
                '<div class="drag">'
                '<img class="drag-app" src="' + LANDING_ASSET_BASE + '/omi-icon.png"'
                ' alt="Omi" width="66" height="66">'
                '<span class="drag-arrow"></span>'
                '<span class="drop-target">'
                '<img src="' + LANDING_ASSET_BASE + '/apps-folder.png" alt="Applications"'
                ' width="60" height="60"></span>'
                '</div>',
                'Drag the <b>Omi</b> icon into<br>your <b>Applications</b> folder',
            ),
            (
                '<div class="finder">'
                '<div class="finder-bar"><i></i><i></i><i></i><span>Applications</span></div>'
                '<div class="app-row"><span class="app-dot"></span><span>Notes</span></div>'
                '<div class="app-row is-omi">'
                '<img src="' + LANDING_ASSET_BASE + '/omi-icon.png" alt="" width="22" height="22">'
                '<span>Omi</span></div>'
                '<div class="app-row"><span class="app-dot"></span><span>Safari</span></div>'
                '</div>',
                'Open <b>Omi</b> from your<br><b>Applications</b> folder',
            ),
        ]

    cards = []
    for index, (art, caption) in enumerate(panels, start=1):
        cards.append(
            f'<li class="step"><span class="step-num">{index}</span>'
            f'<div class="step-art">{art}</div>'
            f'<p class="step-caption">{caption}</p></li>'
        )
    return "".join(cards)


# Product Hunt launch badge for "Omi Desktop" — shown on the download landing page
# only during the launch day, then it disappears on its own. Product Hunt days run
# midnight-to-midnight Pacific, so the window closes at 2026-09-04 07:00 UTC (Sep 3 PDT).
# One-time launch scaffolding: delete this constant, _product_hunt_badge_html, and its
# tests once the launch window has passed.
PRODUCT_HUNT_BADGE_ENDS_AT = datetime(2026, 9, 4, 7, 0, 0, tzinfo=timezone.utc)
PRODUCT_HUNT_POST_URL = (
    "https://www.producthunt.com/products/open-source-ai-necklace-friend?embed=true"
    "&utm_source=badge-featured&utm_medium=badge&utm_campaign=badge-omi-desktop-2"
)
PRODUCT_HUNT_BADGE_IMAGE = "https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1240025&theme=dark"


def product_hunt_badge_html(now: Optional[datetime] = None) -> str:
    """Render the Product Hunt badge while the launch window is open, else nothing.

    Product Hunt bakes the upvote count into the SVG itself, so the embed snippet's
    fixed `t` cache-buster would pin every visitor to whatever count was rendered the
    first time they loaded the page. Bucketing `t` by the hour keeps the count moving
    through the launch day without re-fetching the badge on every request.
    """
    current = now or datetime.now(timezone.utc)
    if current >= PRODUCT_HUNT_BADGE_ENDS_AT:
        return ""
    hour_bucket = int(current.timestamp()) // 3600
    return (
        f'<a class="ph-badge" href="{PRODUCT_HUNT_POST_URL}" target="_blank" rel="noopener noreferrer">'
        f'<img alt="Omi Desktop - Ask your Mac anything you saw or heard | Product Hunt" '
        f'width="250" height="54" src="{PRODUCT_HUNT_BADGE_IMAGE}&t={hour_bucket}"></a>'
    )


def download_landing_html(
    dmg_url: str, channel: str = "stable", version: str = "", platform: str = "macos", notice: str = ""
) -> str:
    """Generate an HTML landing page that auto-triggers the installer download."""
    channel_label = "Beta " if channel == "beta" else ""
    version_display = f"v{version}" if version else ""
    notice_html = f'<p class="notice">{notice}</p>' if notice else ""
    product_hunt_html = product_hunt_badge_html()
    os_name = "Windows" if platform == "windows" else "macOS"
    install_steps = install_steps_html(platform)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Download Omi {channel_label}for {os_name}</title>
    <meta http-equiv="refresh" content="2;url={dmg_url}">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #0a0a0a; color: #fff; display: flex; align-items: center;
               justify-content: center; min-height: 100vh; text-align: center; }}
        .container {{ max-width: 960px; padding: 40px 24px; }}
        h1 {{ font-size: 30px; font-weight: 600; letter-spacing: -0.015em;
              text-wrap: balance; margin-bottom: 8px; }}
        .status-chip {{ display: inline-flex; align-items: center; gap: 7px;
                        padding: 5px 12px 5px 10px; border-radius: 999px;
                        background: #161616; border: 1px solid #262626;
                        color: #9a9a9a; font-size: 11px; font-weight: 600;
                        letter-spacing: 0.07em; text-transform: uppercase;
                        margin-bottom: 18px; }}
        .status-dot {{ width: 12px; height: 12px; border-radius: 50%; flex: none;
                       border: 2px solid #3a3a3a; border-top-color: #9a9a9a;
                       animation: spin 0.8s linear infinite; }}
        .done .status-chip {{ color: #4ade80; border-color: rgba(74,222,128,0.35);
                              background: rgba(74,222,128,0.08); }}
        .done .status-dot {{ animation: none; border: none; width: 13px; height: 13px;
                             background: #4ade80; position: relative; }}
        .done .status-dot::after {{ content: ""; position: absolute; left: 4px; top: 1.5px;
                                    width: 3px; height: 7px; border: solid #0a0a0a;
                                    border-width: 0 2px 2px 0; transform: rotate(45deg); }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .meta {{ color: #6a6a6a; font-size: 13px; margin-bottom: 26px; }}
        .notice {{ color: #fbbf24; font-size: 14px; margin-bottom: 20px; }}
        .download-link {{ color: #8fa6ff; text-decoration: none; }}
        .download-link:hover {{ text-decoration: underline; }}
        .video-container {{ margin-top: 32px; border-radius: 12px; overflow: hidden;
                            background: #151515; display: none; }}
        .video-container video {{ width: 100%; display: block; }}
        .video-label {{ color: #888; font-size: 13px; padding: 12px 16px; text-align: center; }}
        .steps {{ list-style: none; display: grid; grid-template-columns: repeat(3, 1fr);
                  gap: 28px; margin-top: 40px; padding: 0; }}
        .steps-title {{ font-size: 17px; font-weight: 600; color: #fff; margin-top: 44px; }}
        .steps-sub {{ font-size: 13px; color: #666; margin-top: 6px; }}
        .step {{ display: flex; flex-direction: column; align-items: center; }}
        .step-num {{ width: 30px; height: 30px; border-radius: 50%; background: #f2f2f2;
                     border: none; color: #0a0a0a; font-size: 14px; font-weight: 700;
                     display: flex; align-items: center; justify-content: center;
                     margin-bottom: 14px; font-variant-numeric: tabular-nums; }}
        .step-art {{ position: relative; width: 100%; height: 168px; border-radius: 14px;
                     background: #141414; border: 1px solid #232323; display: flex;
                     align-items: center; justify-content: center; overflow: hidden; }}
        .step-caption {{ margin-top: 14px; font-size: 13px; line-height: 1.55; color: #8a8a8a; }}
        .step-caption b {{ color: #e6e6e6; font-weight: 600; }}
        .finder {{ width: 86%; border-radius: 9px; overflow: hidden; background: #1d1d1f;
                   border: 1px solid #2f2f31; text-align: left; }}
        .finder-bar {{ display: flex; align-items: center; gap: 5px; padding: 7px 9px;
                       background: #262628; border-bottom: 1px solid #333; }}
        .finder-bar i {{ width: 7px; height: 7px; border-radius: 50%; background: #3f3f42; }}
        .finder-bar span {{ margin-left: 6px; font-size: 10px; color: #8a8a8f;
                            letter-spacing: 0.02em; }}
        .finder-row, .app-row {{ display: flex; align-items: center; gap: 8px;
                                 padding: 7px 10px; font-size: 12px; color: #d0d0d4; }}
        .dmg-glyph {{ width: 20px; height: 20px; border-radius: 4px; flex: none;
                      background: linear-gradient(160deg, #f4f4f6, #c9ccd6);
                      box-shadow: inset 0 0 0 1px rgba(0,0,0,0.18); }}
        .app-dot {{ width: 18px; height: 18px; border-radius: 5px; flex: none; background: #333336; }}
        .app-row.is-omi {{ background: #2f6bff; color: #fff; border-radius: 5px;
                           margin: 0 5px; font-weight: 500; }}
        .app-row img, .finder-row img {{ border-radius: 5px; flex: none; }}
        .cursor {{ position: absolute; left: 52%; top: 58%;
                   filter: drop-shadow(0 1px 3px rgba(0,0,0,0.75)); }}
        .app-row.is-omi {{ position: relative; }}
        .drag {{ display: flex; align-items: center; gap: 14px; }}
        .drag-app {{ border-radius: 14px; }}
        .drag-arrow {{ width: 30px; height: 2px; background: #6a6a6e; position: relative; }}
        .drag-arrow::after {{ content: ""; position: absolute; right: -2px; top: -4px;
                              border: 5px solid transparent; border-left-color: #6a6a6e; }}
        .drop-target {{ width: 84px; height: 84px; border-radius: 14px; display: flex;
                        align-items: center; justify-content: center;
                        border: 2px dashed #4a4a4e; }}
        .win-file {{ display: flex; flex-direction: column; align-items: center; gap: 8px; }}
        .win-file-glyph {{ width: 52px; height: 62px; border-radius: 6px; display: flex;
                           align-items: center; justify-content: center; font-size: 11px;
                           font-weight: 700; color: #4b5563;
                           background: linear-gradient(160deg, #f4f4f6, #c9ccd6); }}
        .win-file-name {{ font-size: 12px; color: #d0d0d4; }}
        .win-dialog {{ width: 78%; border-radius: 9px; background: #1d1d1f;
                       border: 1px solid #2f2f31; padding: 12px; text-align: left; }}
        .win-dialog-title {{ font-size: 12px; color: #d0d0d4; margin-bottom: 8px; }}
        .win-dialog-link {{ font-size: 11px; color: #6C8FFF; margin-bottom: 10px; }}
        .win-dialog-run {{ display: inline-block; font-size: 11px; color: #fff; padding: 4px 10px;
                           border-radius: 5px; background: #2f6bff; }}
        @media (max-width: 720px) {{
          .steps {{ grid-template-columns: 1fr; gap: 22px; }}
          .step-art {{ height: 150px; }}
        }}
        .ph-badge {{ display: inline-block; margin-bottom: 4px; line-height: 0;
                     opacity: 0.92; transition: opacity 0.15s ease; }}
        .ph-badge:hover {{ opacity: 1; }}
        .ph-badge img {{ width: 250px; height: 54px; }}
        .discord {{ margin-top: 24px; font-size: 14px; color: #888; }}
        .discord a {{ color: #5865F2; text-decoration: none; }}
        .discord a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <p class="status-chip" id="status-chip">
            <span class="status-dot" aria-hidden="true"></span><span id="status-text">Downloading</span>
        </p>
        <h1>Omi {channel_label}for {os_name}</h1>
        <p class="meta">{version_display} &middot; Didn&rsquo;t start?
            <a class="download-link" href="{dmg_url}">Download manually</a></p>
        {notice_html}
        {product_hunt_html}
        <div class="video-container" id="demo-video">
            <video autoplay muted loop playsinline>
                <source src="https://storage.googleapis.com/omi_macos_updates/omi-demo.mp4" type="video/mp4">
            </video>
            <p class="video-label">See how Omi works</p>
        </div>
        <h2 class="steps-title">Just a few steps left</h2>
        <p class="steps-sub">Takes about 20 seconds.</p>
        <ol class="steps">{install_steps}</ol>
        <p class="discord">Need help? Join our <a href="https://discord.com/invite/8MP3b9ymvx">Discord community</a></p>
    </div>
    <script>
        setTimeout(function() {{
            window.location.href = "{dmg_url}";
            document.body.classList.add("done");
            document.getElementById("status-text").textContent = "In your Downloads";
            document.getElementById("demo-video").style.display = "block";
        }}, 2000);
    </script>
</body>
</html>"""
