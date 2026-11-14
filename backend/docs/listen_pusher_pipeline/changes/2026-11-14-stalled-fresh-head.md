# Ready fresh work behind an unready fresh or legacy head

An owner's oldest pending GPU row can remain unready while a later provider
backlog row is ready and held. The bounded head-wait path selects that held row
repeatedly, hiding ready fresh work behind it. The existing transactional fresh
selection only runs when the overall head is classified as catch-up or held
provider backlog, so it does not address this fresh-head or unstamped-head case.

After an expired head wait selects held provider stock, retry selection through
the existing transactional fresh queries. Both selection and commit use the same
transaction, and the selected fresh row must satisfy its own head wait. The held
provider result stays uncommitted. No new class is derived or persisted.

This shared merge path runs in backend-integration and the GKE batch worker, over
Firestore and Postgres; the simulator uses the same merge implementation. No
stored schema, result-log predecessor, projection fence or privacy rule changes.
Fresh rows and legacy heads retain the configured head wait; turning it off
preserves strict order. The existing
`BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED=false` switch disables the additional
selection. A missing query index backs off and leaves the backlog held.

This change addresses selection after an owner is offered. It does not replace
the durable discovery cursor, repair policy-held retries or bypass privacy.
