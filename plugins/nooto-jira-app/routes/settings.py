"""User settings routes — slice D owns this file.

Settings hash key: `jira:settings:{uid}` with fields:
    enabled, autofile, default_project_key, quiet_hours

Routes:
    GET  /settings?uid=...              HTML form (mirrors ClickUp setup style)
    POST /settings                      update settings
    POST /settings/default-site         multi-site picker → set default_cloud_id
"""

import logging
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import db

router = APIRouter()
log = logging.getLogger("nooto-jira-app.settings")


def _settings_key(uid: str) -> str:
    return f"jira:settings:{uid}"


def _save_settings(uid: str, mapping: dict[str, str]) -> None:
    r = db.get_redis()
    if not r:
        log.warning("Redis unavailable; cannot persist settings for uid=%s", uid)
        return
    try:
        # Replace the hash so unchecked checkboxes reset.
        pipe = r.pipeline()
        pipe.delete(_settings_key(uid))
        if mapping:
            pipe.hset(_settings_key(uid), mapping=mapping)
        pipe.execute()
    except Exception as e:
        log.warning("settings save failed for uid=%s: %s", uid, e)


# ── HTML form ─────────────────────────────────────────────────────────────


def _render_settings_html(
    uid: str,
    settings: dict[str, str],
    *,
    flash: Optional[str] = None,
) -> str:
    enabled = settings.get("enabled", "true") != "false"
    autofile = settings.get("autofile") == "true"
    default_project_key = settings.get("default_project_key", "") or ""
    quiet_hours = settings.get("quiet_hours", "") or ""
    flash_html = f'<div class="status success">{flash}</div>' if flash else ""
    enabled_attr = "checked" if enabled else ""
    autofile_attr = "checked" if autofile else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jira settings · Nooto</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--jira-blue:#2684FF;--bg:#0D0D0D;--surface:#171717;--border:#2A2A2A;--text:#fff;--muted:#9B9B9B;--success:#4ADE80;}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--text);padding:20px;min-height:100vh;
  background-image:radial-gradient(ellipse 80% 50% at 50% -20%, rgba(38,132,255,0.15), transparent);}}
.container{{max-width:480px;margin:0 auto;padding:20px}}
.header{{text-align:center;margin-bottom:32px;padding-top:20px}}
h1{{font-size:24px;font-weight:700;margin-bottom:6px;letter-spacing:-0.5px}}
.subtitle{{color:var(--muted);font-size:14px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:24px;margin-bottom:16px}}
.field{{display:flex;flex-direction:column;gap:6px;margin-bottom:18px}}
.field label{{font-weight:600;font-size:14px}}
.field .hint{{color:var(--muted);font-size:12px}}
input[type=text]{{width:100%;padding:11px 14px;border-radius:10px;border:1px solid var(--border);background:#0F0F0F;color:var(--text);font-family:inherit;font-size:14px}}
input[type=text]:focus{{outline:0;border-color:var(--jira-blue)}}
.toggle{{display:flex;align-items:center;gap:10px;margin-bottom:18px}}
.toggle input{{width:18px;height:18px;accent-color:var(--jira-blue)}}
.btn{{display:inline-flex;align-items:center;justify-content:center;width:100%;padding:13px 20px;border-radius:12px;border:0;background:var(--jira-blue);color:#fff;font-weight:600;font-size:15px;cursor:pointer;font-family:inherit}}
.btn:hover{{background:#0052CC}}
.status{{padding:10px 14px;border-radius:10px;font-size:13px;margin-bottom:16px}}
.status.success{{background:rgba(74,222,128,0.1);color:var(--success);border:1px solid rgba(74,222,128,0.3)}}
</style></head>
<body>
<div class="container">
  <div class="header">
    <h1>Jira settings</h1>
    <div class="subtitle">Tune how Nooto suggests and files Jira tickets for you.</div>
  </div>
  {flash_html}
  <form method="post" action="/settings" class="card">
    <input type="hidden" name="uid" value="{uid}">
    <div class="toggle">
      <input type="checkbox" id="enabled" name="enabled" value="true" {enabled_attr}>
      <label for="enabled">Enable proactive ticket suggestions</label>
    </div>
    <div class="toggle">
      <input type="checkbox" id="autofile" name="autofile" value="true" {autofile_attr}>
      <label for="autofile">Auto-file high-confidence tickets (>=85%)</label>
    </div>
    <div class="field">
      <label for="default_project_key">Default project key</label>
      <input type="text" id="default_project_key" name="default_project_key" value="{default_project_key}" placeholder="e.g. NTO">
      <div class="hint">Used as a fallback when no project is mentioned.</div>
    </div>
    <div class="field">
      <label for="quiet_hours">Quiet hours</label>
      <input type="text" id="quiet_hours" name="quiet_hours" value="{quiet_hours}" placeholder="22:00-07:00">
      <div class="hint">No notifications during this window. Leave blank to disable.</div>
    </div>
    <button type="submit" class="btn">Save settings</button>
  </form>
</div>
</body></html>"""


# ── Routes ────────────────────────────────────────────────────────────────


@router.get("/settings", response_class=HTMLResponse)
async def get_settings(uid: str = "", saved: int = 0):
    if not uid:
        raise HTTPException(status_code=400, detail="uid is required")
    settings = db.get_settings(uid)
    flash = "Saved." if saved else None
    return HTMLResponse(_render_settings_html(uid, settings, flash=flash))


@router.post("/settings")
async def post_settings(
    request: Request,
    uid: str = Form(...),
    enabled: Optional[str] = Form(None),
    autofile: Optional[str] = Form(None),
    default_project_key: Optional[str] = Form(None),
    quiet_hours: Optional[str] = Form(None),
):
    mapping: dict[str, str] = {
        "enabled": "true" if (enabled == "true") else "false",
        "autofile": "true" if (autofile == "true") else "false",
    }
    if default_project_key and default_project_key.strip():
        mapping["default_project_key"] = default_project_key.strip()
    if quiet_hours and quiet_hours.strip():
        mapping["quiet_hours"] = quiet_hours.strip()
    _save_settings(uid, mapping)

    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return JSONResponse({"status": "ok", "settings": mapping})
    return RedirectResponse(url=f"/settings?uid={uid}&saved=1", status_code=303)


@router.post("/settings/default-site")
async def post_default_site(
    uid: str = Form(...),
    cloud_id: str = Form(...),
):
    if not uid or not cloud_id:
        raise HTTPException(status_code=400, detail="uid and cloud_id are required")
    db.set_default_cloud_id(uid, cloud_id)
    # Send the user back to the setup page for confirmation.
    return RedirectResponse(url=f"/setup/jira?uid={uid}", status_code=303)
