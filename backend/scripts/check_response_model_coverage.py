#!/usr/bin/env python3
"""Phase 1.1 gate: assert every FastAPI route is either typed (response_model)
or explicitly allowlisted as legitimately non-JSON.

Exit codes:
  0 — every route is typed or justified.
  1 — one or more routes are silently untyped (no response_model, not allowlisted).
  2 — the allowlist is stale (lists a route that no longer exists or now has response_model).

The allowlist below is the single source of truth for "which routes are legit
non-JSON and why". Every entry MUST have a concrete reason. Do not add entries to
keep the gate green — if a route can carry a response_model, type it instead.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROUTER_DIR = pathlib.Path(__file__).resolve().parent.parent / "routers"
METHODS = {"get", "post", "put", "patch", "delete", "api_route", "head", "options", "websocket"}

# (file, function_name) -> reason. Functions may appear under multiple paths
# (e.g. well-known metadata); keyed by function name per file.
LEGIT_NON_JSON: dict[tuple[str, str], str] = {
    # --- WebSockets / SSE streaming ---
    ("transcribe.py", "listen_handler"): "WebSocket audio stream",
    ("transcribe.py", "web_listen_handler"): "WebSocket audio stream",
    ("pusher.py", "websocket_endpoint_trigger"): "WebSocket audio stream",
    ("chat.py", "create_voice_message_stream"): "StreamingResponse audio",
    ("chat.py", "transcribe_voice_message_stream"): "StreamingResponse audio",
    ("mcp_sse.py", "mcp_streamable_http"): "SSE stream",
    ("mcp_sse.py", "mcp_sse_get"): "SSE stream",
    ("mcp_sse.py", "mcp_sse_head"): "SSE stream",
    # --- OAuth / redirect callbacks (return RedirectResponse or HTML) ---
    ("auth.py", "auth_authorize"): "OAuth authorize redirect",
    ("auth.py", "auth_callback_google"): "OAuth callback redirect",
    ("auth.py", "auth_callback_apple_post"): "OAuth callback redirect",
    ("auth.py", "auth_token"): "OAuth token endpoint (application/x-www-form-urlencoded)",
    ("oauth.py", "oauth_authorize"): "OAuth authorize redirect",
    ("mcp_sse.py", "mcp_authorize"): "OAuth authorize redirect",
    ("x_connector.py", "x_oauth_callback"): "OAuth callback redirect",
    ("integrations.py", "oauth_callback"): "OAuth callback redirect",
    ("apps.py", "mcp_oauth_callback"): "OAuth callback redirect",
    ("task_integrations.py", "todoist_oauth_callback"): "OAuth callback redirect",
    ("task_integrations.py", "asana_oauth_callback"): "OAuth callback redirect",
    ("task_integrations.py", "google_tasks_oauth_callback"): "OAuth callback redirect",
    ("task_integrations.py", "clickup_oauth_callback"): "OAuth callback redirect",
    ("payment.py", "stripe_return"): "Stripe redirect callback",
    ("payment.py", "stripe_success"): "Stripe redirect callback",
    ("payment.py", "stripe_cancel"): "Stripe redirect callback",
    ("payment.py", "portal_return"): "Stripe redirect callback",
    # --- Binary / non-JSON content ---
    ("metrics.py", "metrics"): "Prometheus text/plain exposition",
    ("phone_calls.py", "twiml_voice_webhook"): "TwiML XML (voice webhook)",
    ("updates.py", "get_desktop_appcast_xml"): "XML appcast (Sparkle update feed)",
    ("updates.py", "download_latest_desktop_release"): "binary file download (StreamingResponse)",
    ("updates.py", "download_beta_desktop_release"): "binary file download (StreamingResponse)",
    ("tts.py", "tts_synthesize"): "binary audio stream (StreamingResponse)",
    ("sync.py", "download_audio_file_endpoint"): "binary audio file download (StreamingResponse)",
    ("users.py", "export_all_user_data"): "StreamingResponse data-export download",
    # --- 204 No Content (genuine empty-body deletes; FastAPI rejects response_model+204) ---
    ("developer.py", "delete_key"): "204 No Content",
    ("folders.py", "delete_folder"): "204 No Content",
    ("integrations.py", "delete_integration"): "204 No Content",
    ("mcp.py", "delete_key"): "204 No Content",
    ("mcp.py", "revoke_oauth_grant"): "204 No Content",
    ("action_items.py", "delete_action_item"): "204 No Content",
    ("task_integrations.py", "delete_task_integration"): "204 No Content",
    ("users.py", "delete_person_endpoint"): "204 No Content",
    ("mcp_sse.py", "mcp_delete_session"): "raw Response (MCP session delete, no JSON body)",
    # --- OAuth / OpenID well-known discovery documents (spec-defined, not app-consumed) ---
    ("mcp_sse.py", "oauth_protected_resource_metadata"): "RFC 9728 OAuth discovery JSON (spec-defined)",
    ("mcp_sse.py", "oauth_protected_resource_metadata_head"): "RFC 9728 OAuth discovery JSON (spec-defined)",
    ("mcp_sse.py", "oauth_authorization_server_metadata"): "RFC 8414 OAuth discovery JSON (spec-defined)",
    ("mcp_sse.py", "oauth_authorization_server_metadata_head"): "RFC 8414 OAuth discovery JSON (spec-defined)",
    ("mcp_sse.py", "openai_apps_challenge"): "OpenAI apps verification challenge (static asset)",
    # --- Cloud Tasks job runners (OIDC-verified internal, return JSONResponse acks directly) ---
    ("sync.py", "run_sync_job"): "Cloud Tasks job runner (OIDC-verified internal, JSONResponse acks)",
    ("sync.py", "run_audio_merge_job"): "Cloud Tasks job runner (OIDC-verified internal, JSONResponse acks)",
    ("sync.py", "sync_local_files"): "sync dispatch (JSONResponse, multi-mode dispatch)",
    ("omni_relay.py", "omni_relay"): "relay proxy (forwards to upstream, JSONResponse passthrough)",
}


def find_routes() -> list[dict]:
    routes = []
    for p in sorted(ROUTER_DIR.glob("*.py")):
        if p.name == "__init__.py":
            continue
        source = p.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            # Treat parse failures as gate failures so untyped routes cannot
            # slip through in files with syntax errors.
            raise SystemExit(f"❌ {p.name}: syntax error blocks response_model coverage scan: {exc}")
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                func = dec.func
                if not isinstance(func, ast.Attribute):
                    continue
                if func.attr not in METHODS:
                    continue
                has_rm = any(k.arg == "response_model" for k in dec.keywords)
                routes.append({"file": p.name, "fn": node.name, "has_rm": has_rm, "line": node.lineno})
    return routes


def main() -> int:
    routes = find_routes()
    untyped = [r for r in routes if not r["has_rm"]]
    unjustified = []
    for r in untyped:
        key = (r["file"], r["fn"])
        if key not in LEGIT_NON_JSON:
            unjustified.append(r)

    # Stale allowlist entries: allowlisted routes that now have response_model
    # or no longer exist.
    route_keys = {(r["file"], r["fn"]) for r in routes}
    untyped_keys = {(r["file"], r["fn"]) for r in untyped}
    stale = []
    for key in LEGIT_NON_JSON:
        if key not in route_keys:
            stale.append((key, "route no longer exists"))
        elif key in untyped_keys:
            pass  # correctly allowlisted
        else:
            stale.append((key, "route now has response_model — remove from allowlist"))

    typed = len([r for r in routes if r["has_rm"]])
    total = len(routes)
    allowlisted = len(untyped) - len(unjustified)
    print(f"response_model coverage: {typed}/{total} ({100 * typed / total:.1f}% of all routes)")
    print(f"  typed: {typed}  |  allowlisted non-JSON: {allowlisted}  |  unjustified: {len(unjustified)}")

    exit_code = 0
    if unjustified:
        print("\n❌ UNJUSTIFIED untyped routes (add response_model or allowlist with reason):")
        for r in unjustified:
            print(f"  {r['file']}:{r['line']} {r['fn']}")
        exit_code = 1
    if stale:
        print("\n⚠️  STALE allowlist entries (clean up):")
        for key, reason in sorted(stale):
            print(f"  {key[0]}::{key[1]} — {reason}")
        exit_code = max(exit_code, 2)
    if exit_code == 0:
        print("\n✅ Every route is typed or justified.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
