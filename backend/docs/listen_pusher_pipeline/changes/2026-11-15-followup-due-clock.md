# Projection follow-up discovery scheduling

Persisted/ready projection follow-ups gain a separate durable due-time hint so
unchanged incomplete work can leave the discovery query for at most60seconds.
Targeted recovery and receipt/privacy/ledger/completion fences remain unchanged.
The reader uses legacy discovery until all writer hosts are deployed and the
separately admitted bounded backfill publishes its versioned completion marker.
Existing backoff=0 restores legacy reads. See the deployment, rollback and real
Firestore test contract in [the runbook](../../runbooks/projection-followup-due-clock.md).
No production activation or measured-saving claim accompanies this source change.
