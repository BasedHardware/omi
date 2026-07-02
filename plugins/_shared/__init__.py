"""Shared code used by all the AI Clone chat-platform plugins.

Currently:
- auth: bearer-token gate (`require_bearer` FastAPI dependency)
- persona_client: thin client to the backend /v2/integrations/...
  /persona-chat route (used by every plugin's auto-reply dispatch)
- plugin_discovery: writes ~/.config/omi/ai-clone-plugin-<type>.json
  on plugin startup so the desktop can auto-fill its settings
- storage: small per-plugin key-value store helper
- http_client: shared httpx.AsyncClient with connection pooling
"""
