"""Shared bounds for hosted MCP tool inputs, schemas, and the POST transport."""

MCP_MEMORY_LIST_DEFAULT_LIMIT = 20
MCP_MEMORY_LIST_MAX_LIMIT = 100
MCP_MEMORY_LIST_MAX_SCAN = 200
MCP_CONVERSATION_LIST_MAX_LIMIT = 100
MCP_CONVERSATION_FETCH_DEFAULT_MAX_SEGMENTS = 120
MCP_CONVERSATION_FETCH_MAX_SEGMENTS = 500
MCP_CONVERSATION_FETCH_DEFAULT_MAX_CHARS = 24_000
MCP_CONVERSATION_FETCH_MAX_CHARS = 100_000
MCP_CONVERSATION_SEARCH_SNIPPET_CHARS = 240
MCP_CONVERSATION_BATCH_MAX_IDS = 20
# Firestore document id bound; keeps `not_found` echoes inside the response budget.
MCP_CONVERSATION_ID_MAX_BYTES = 1500
MCP_CONVERSATION_BATCH_RESPONSE_MAX_CHARS = 120_000
MCP_MEMORY_BATCH_MAX_ITEMS = 25
MCP_SCREEN_ACTIVITY_OBSERVATION_GAP_SECONDS = 300
MCP_SCREEN_ACTIVITY_TOP_TITLES = 10

# REST /v1/mcp detail bounds: released REST clients fetch the full transcript
# in one shot, so the shared bounded reader runs with much wider caps than the
# hosted tool defaults while still bounding the response.
MCP_REST_CONVERSATION_MAX_SEGMENTS = 4096
MCP_REST_CONVERSATION_MAX_CHARS = 500_000

# JSON-RPC batch (array) requests are a pre-2025-06-18 transport feature. The
# cap keeps a single POST from fanning out into unbounded per-message work.
MCP_MAX_BATCH_MESSAGES = 20
