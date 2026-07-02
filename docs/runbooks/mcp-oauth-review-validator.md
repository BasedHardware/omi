# MCP OAuth Review Validator

Use this before submitting or exporting a ChatGPT MCP review package:

```bash
cd backend
python scripts/validate_mcp_oauth_review_config.py /path/to/submission.json
```

If you captured a live `tools/list` response for the same scope set, compare it too:

```bash
python scripts/validate_mcp_oauth_review_config.py /path/to/submission.json --live-tools-json /path/to/tools-list.json
```

The validator fails on rejected legacy client IDs such as `omi`, token auth mismatches, null `oauth_client` blocks, raw secret fields, and optional tool metadata drift. It reports field paths only; it does not print secret values.
