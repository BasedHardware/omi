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
   query. A composite requirement includes a `create_composite=` suggestion;
   a single-field collection-group requirement may instead include
   `create_exemption=`.
2. Decode the URL-safe base64 suggestion and confirm its collection or
   collection group, fields, scope, and direction against the actual query.
   The real-Firestore oracle can reproduce and classify the platform
   suggestion without provisioning it. For `create_exemption=`, declare the
   matching field requirement in the registry so generation produces the
   `fieldOverrides` entry; do not model it as a composite query spec.
3. Add or update the requirement in
   `backend/database/firestore_index_registry.py`, then run
   `backend/.venv/bin/python backend/scripts/generate_firestore_indexes.py
   --write`. Every generated composite index entry must end in `__name__`.
4. Open a PR for the registry and generated `firestore.indexes.json`. The
   Firestore index workflow applies declared requirements after its
   production approval. Do not create an index directly from the alert
   response.
5. After the requirement is ready, retry the affected request and confirm it
   succeeds. Record the incident and index PR in the alert policy notes.

## Validate the alert signal

After deployment, inspect the exact metric expression for a known incident
window and a known-good window. Record both evaluated counts with their time
ranges in the policy documentation, and confirm the incident count is greater
than zero while the known-good count is zero. The alert is provisioned and its
stored condition is verified by the deployment script; historical live signal
proof remains a post-deploy operational check.
