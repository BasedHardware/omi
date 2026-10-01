# Firestore missing-index alert

The production backend deploy provisions the `firestore_missing_index_errors`
Cloud Logging counter and its Cloud Monitoring alert in `based-hardware`. The
counter matches Cloud Run revision log entries containing
`The query requires an index` in `textPayload` or `jsonPayload.message`, and
labels each series with its Cloud Run `service_name`. The alert fires when any
service records one or more matching errors in a five-minute aligned window.
It routes through `SYNC_BACKFILL_ALERT_NOTIFICATION_CHANNELS`.

## Respond to an alert

1. Open the affected Cloud Run revision logs and find the failed Firestore
   query. The Firestore error includes a `create_composite=` URL with the
   suggested composite index.
2. Decode the URL-safe base64 value after `create_composite=`. Its field order
   bytes use `1` for ascending and `2` for descending. Confirm the collection,
   fields, and order against the query before changing the registry.
3. Add the query spec to `backend/database/firestore_index_registry.py`, then
   run `backend/.venv/bin/python backend/scripts/generate_firestore_indexes.py
   --write`. Every generated index entry must end in `__name__`.
4. Open a PR for the registry and generated `firestore.indexes.json`. The
   Firestore index workflow applies declared indexes after its production
   approval. Do not create an index directly from the alert response.
5. After the index is ready, retry the affected request and confirm it
   succeeds. Record the incident and index PR in the alert policy notes.

## Validate the alert signal

After deployment, inspect the exact metric expression for a known incident
window and a known-good window. Record both evaluated counts with their time
ranges in the policy documentation, and confirm the incident count is greater
than zero while the known-good count is zero. The alert is provisioned and its
stored condition is verified by the deployment script; historical live signal
proof remains a post-deploy operational check.
