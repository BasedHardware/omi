# MCP OAuth Review Validator

Use this before submitting or exporting a ChatGPT MCP review package:

```bash
cd backend
python scripts/validate_mcp_oauth_review_config.py /path/to/submission.json
```

## Google OAuth Secret Rotation

Rotating `GOOGLE_CLIENT_SECRET` in Secret Manager does not update Firebase
Auth's Google provider copy. After adding a new Secret Manager version, sync the
Firebase provider before disabling the old version:

```bash
cd backend
python scripts/sync_firebase_google_provider_secret.py --project based-hardware
python scripts/sync_firebase_google_provider_secret.py --project based-hardware --apply
```

The first command is a dry run. The apply command patches
`defaultSupportedIdpConfigs/google.com` using `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET` from Secret Manager without printing secrets. If the
provider copy drifts, FirebaseUI sign-in on the MCP OAuth consent page fails
with `invalid_client` even when backend Google OAuth still works.

If you captured a live `tools/list` response for the same scope set, compare it too:

```bash
python scripts/validate_mcp_oauth_review_config.py /path/to/submission.json --live-tools-json /path/to/tools-list.json
```

The validator fails on rejected legacy client IDs such as `omi`, token auth mismatches, null `oauth_client` blocks, raw secret fields, and optional tool metadata drift. It reports field paths only; it does not print secret values.
