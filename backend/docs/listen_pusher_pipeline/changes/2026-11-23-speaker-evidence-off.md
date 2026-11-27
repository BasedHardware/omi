# Speaker evidence retirement, first production code roll

SCA-3684 pins `SPEAKER_EVIDENCE_MODE=off` on the backend, sync, sync-backfill, integration and projection-pump Cloud Run revisions, the X sync job, the listen and pusher charts, and the pull worker's isolated sync job. The pump inherits the integration binding. Dormant listen tracks need the reviewed chart and a template readback before activation.

Off stops the finalize comparison, sampled encrypted evidence writes, optional evidence reads, clip embedding cache and name-link and profile comparisons. Embedding requests still run. Home background visibility, salience, media classification and notes may consume sampled evidence even with zero speaker serving users. Verify their output alongside persisted speaker labels, manual corrections and successful name links.

Shipping obtains the user-visible and derived-data ruling. Release approves each normal code roll and records its effective binding, serving revision or pod/job template and UTC time. Roll back to the previous revision or Helm release if a guard changes. Restore the previous job template before its next execution. Retain all four controls through 24 continuous hours from the last verified reader. A return to shadow or serve restarts the interval.
