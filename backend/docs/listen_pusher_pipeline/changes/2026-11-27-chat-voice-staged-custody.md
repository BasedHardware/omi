# Chat voice staged-input custody

SCA-4775 moves chat voice scratch cleanup from URL creation to actual consumer termination. Delayed VAD/download/provider work therefore cannot delete the only staged generation before use. Expected silence and terminal provider failure also schedule cleanup, and SSE cancellation leaves the executor worker in control until it exits.

Cleanup uses the uploaded GCS generation rather than a path alone. Account deletion still takes precedence and covers both direct multipart (`/tmp/{uid}_…`) and decoded (`syncing/{uid}/…`) layouts in the configured temporary and derived buckets. Signed URL expiry remains 15 minutes; no consent, transcript-retention or historical-deletion behavior changes.

The existing process-local janitor is still best-effort and does not establish a crash-durable retention bound. Before release, follow `../../runbooks/audio-cleanup-custody.md` for read-only lifecycle, soft-delete and versioning checks. After release, compare only bounded aggregate `omi_transcription_completed_total{route="voice_chat_sse"}` and `omi_transcription_completed_total{route="voice_rest_multipart"}` outcomes and latency on the new serving revision; do not export account, object, transcript or URL data.
