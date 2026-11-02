"""Shared mobile/desktop setup and consented backup document formatting."""

import html
from collections.abc import Mapping


# Primary summary selection, ported from backend/utils/conversations/summary_selection.py.
# The plugin is a standalone service and cannot import the backend; the shared vectors
# in contracts/parity/conversation_summary.json keep the two in agreement (test_app.py).
def _value(source, key, default=None):
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ''


def render_sections_markdown(sections) -> str:
    section_list = list(sections or [])
    if any(_value(section, 'kind') == 'side_notes' for section in section_list):
        section_list = [s for s in section_list if _value(s, 'kind') != 'side_notes'] + [
            s for s in section_list if _value(s, 'kind') == 'side_notes'
        ]
    rendered = []
    for section in section_list:
        heading = _text(_value(section, 'heading'))
        body = _text(_value(section, 'body_markdown'))
        if heading and body:
            rendered.append(f'## {heading}\n\n{body}')
        elif body:
            rendered.append(body)
    return '\n\n'.join(rendered)


def select_primary_summary(conversation) -> dict:
    """The one primary body that display, copy, sharing and this backup agree on."""
    for result_index, result in enumerate(_value(conversation, 'apps_results', []) or []):
        content = _text(_value(result, 'content'))
        if content:
            app_id = _value(result, 'app_id')
            return {
                'kind': 'app',
                'content': content,
                'app_id': app_id if isinstance(app_id, str) else None,
                'result_index': result_index,
            }
    structured = _value(conversation, 'structured', {}) or {}
    overview = _text(_value(structured, 'overview'))
    sections = render_sections_markdown(_value(structured, 'sections', []) or [])
    if overview and sections and overview == sections:
        return {'kind': 'sections', 'content': sections, 'app_id': None, 'result_index': None}
    if overview:
        return {'kind': 'overview', 'content': overview, 'app_id': None, 'result_index': None}
    if sections:
        return {'kind': 'sections', 'content': sections, 'app_id': None, 'result_index': None}
    return {'kind': 'empty', 'content': '', 'app_id': None, 'result_index': None}


def summary_markdown(conversation) -> str:
    structured = conversation.structured
    date = conversation.finished_at or conversation.created_at
    category = getattr(structured.category, 'value', structured.category)
    body = select_primary_summary(conversation)['content']
    content = f'# {structured.title}\n\n**Date:** {date.isoformat()}\n**Category:** {category}\n\n{body}\n'
    for item in structured.action_items:
        content += f'\n- [{"x" if item.completed else " "}] {item.description}'
    return content + '\n'


def transcript_markdown(conversation) -> str:
    content = f'# Transcript: {conversation.structured.title}\n\n'
    for segment in conversation.transcript_segments:
        speaker = segment.speaker or ('User' if segment.is_user else 'Speaker')
        content += f'**{speaker}** [{segment.start:.1f}–{segment.end:.1f}s]: {segment.text}\n\n'
    return content


def setup_html(settings: dict, connection: dict | None, jobs: list[dict], csrf: str, notice: str = '') -> str:
    escape = html.escape
    status = (connection or {}).get('status', 'disconnected')
    token = f'<input type="hidden" name="csrf" value="{escape(csrf)}">'
    if connection:
        label = 'Retry access revocation' if status == 'revoke_pending' else 'Disconnect pCloud'
        action = f'<form method="post" action="/disconnect">{token}<button class="secondary" type="submit">{label}</button></form>'
    else:
        action = (
            f'<form method="post" action="/auth/pcloud">{token}<button type="submit">Connect pCloud</button></form>'
        )
    rows = []
    for job in jobs:
        count = len(job.get('uploaded', []))
        file_label = 'file' if count == 1 else 'files'
        retry = ''
        if job['state'] in ('failed', 'pending'):
            retry = f'<form method="post" action="/backups/{escape(job["id"])}/retry">{token}<button class="secondary" type="submit">Retry backup</button></form>'
        error = f'<p class="error">{escape(job.get("error") or "")}</p>' if job.get('error') else ''
        rows.append(
            f'<li><strong>{escape(job.get("title") or "Conversation")}</strong><p>{escape(job["state"].replace("_", " ").capitalize())} · {count} {file_label} saved</p>{error}{retry}</li>'
        )
    rows_html = ''.join(rows) or '<li>No backups yet. New conversations appear here after setup is complete.</li>'
    choices = ''.join(
        f'<label class="choice"><input type="checkbox" name="{key}" {"checked" if settings[key] else ""}><span>{label}</span></label>'
        for key, label in [
            ('save_summary', 'Conversation summaries'),
            ('save_transcript', 'Private transcripts — send a copy to pCloud'),
            ('save_audio', 'Saved conversation audio — send a copy to pCloud'),
        ]
    )
    connection_text = (
        f'Connected as {escape(connection.get("email") or "your pCloud account")}'
        if status == 'active'
        else ('Backups stopped. pCloud access revocation is still pending.' if connection else 'Not connected')
    )
    notice_html = f'<p role="status" class="notice">{escape(notice)}</p>' if notice else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>pCloud backup settings · Omi</title><style>
:root{{color-scheme:light;--ink:#202124;--muted:#50545a;--line:#dadce0;--surface:#f8f9fa}}*{{box-sizing:border-box}}body{{margin:0;background:var(--surface);color:var(--ink);font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:650px;margin:auto;padding:32px 20px 64px}}h1{{font-size:28px;line-height:1.2;margin:0 0 16px}}h2{{font-size:20px;margin:32px 0 12px}}p{{margin:8px 0;color:var(--muted);overflow-wrap:anywhere}}label{{display:block;font-weight:600;margin:16px 0 6px}}input[type=text]{{width:100%;padding:12px;border:1px solid #85888c;border-radius:6px;background:white;color:var(--ink);font:inherit}}.choice{{display:flex;gap:12px;align-items:flex-start;font-weight:400}}input[type=checkbox]{{width:20px;height:20px;flex-shrink:0;margin-top:3px;accent-color:#202124}}button{{padding:11px 18px;border:1px solid #202124;border-radius:7px;background:#202124;color:white;font:inherit;font-weight:600;cursor:pointer;margin-top:14px;min-height:44px}}button.secondary{{background:white;color:var(--ink)}}button:hover{{background:#414348;color:white}}button:disabled{{cursor:wait;opacity:.65}}:focus-visible{{outline:3px solid #185abc;outline-offset:3px}}::selection{{background:#d7e3fd;color:#202124}}input{{caret-color:#202124}}ul{{list-style:none;padding:0}}li{{border-top:1px solid var(--line);padding:18px 0;overflow-wrap:anywhere}}.notice{{padding:14px;background:#e8f0fe;color:#174ea6;border-radius:7px}}.error{{color:#a50e0e}}small{{font-size:14px;color:var(--muted)}}fieldset{{border:0;padding:0;margin:20px 0}}legend{{font-weight:600}}@media(max-width:420px){{main{{padding:24px 16px 48px}}button{{width:100%}}}}
</style></head><body><main><h1>pCloud backups</h1>{notice_html}<p>{connection_text}</p>{action}<h2>Choose what to back up</h2><form method="post" action="/settings">{token}<label for="folder">Destination folder</label><input id="folder" type="text" name="folder_name" maxlength="200" value="{escape(settings['folder_name'])}" required><fieldset><legend>Backup preferences</legend>{choices}</fieldset><p>Transcripts and audio stay off until you explicitly enable and save them. Audio is available only when Omi has saved it for that conversation.</p><button type="submit">Save backup preferences</button></form><h2>Recent backups</h2><p>Failed backups retry automatically up to five times. You can also retry below. Pending content expires after seven days.</p><ul>{rows_html}</ul><h2>Disconnecting and privacy</h2><p>Disconnect stops new backups and cancels pending copies. Omi removes local credentials after pCloud confirms revocation; if pCloud is unavailable, encrypted credentials are retained only so you can retry revocation. Omi does not delete files already saved to pCloud.</p><small>Open these settings from Omi on either mobile or desktop to see the same saved connection and backup status.</small></main></body></html>'''
