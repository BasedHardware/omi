# Speaker evidence erasure verification

[Verification runbook](../../runbooks/speaker-evidence-verification.md) · [SCA-4873 implementation and evidence](https://github.com/BasedHardware/omi/pull/26453)

## Writer and sweep sequencing

For one authorized synthetic account, the already sampled writer waits for a fresh account-deletion marker.
After the marker commits, the writer resumes and the existing transaction fence refuses the evidence write.
The authenticated Sync delivery can defer while enqueue acknowledgment or the writer outcome is pending.
Only the matching task can receive completion credit after the full wipe and a checked sweep with zero
remaining evidence children. A duplicate delivery or a second reservation cannot earn additional credit.

## Configuration and rollout

The verification controls default off. After separate Release approval and preflight, the designated Backend
and Sync revisions can be armed for one synthetic account with the UID digest, private token and expiring
control document described in the runbook. Collect revision-scoped aggregate evidence, then clear the arming
configuration and remove the temporary control document. The runbook defines expiry and code removal.

## Verification evidence

The loopback Firestore rehearsal covers a marker refusal, zero marker-present commits, a completed sweep
with zero remaining children, authenticated HTTP 409 deferral, duplicate delivery and a rejected second
reservation. The evidence counter is `omi_speaker_evidence_verification_total{revision,outcome}`.
