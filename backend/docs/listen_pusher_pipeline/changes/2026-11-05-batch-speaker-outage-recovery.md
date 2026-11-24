# Speaker-only wake outage recovery and rollout metrics

Speaker wakes acknowledge transient Firestore claim or settlement failures
without immediately requeuing. The existing dedicated-outbox sweeper repairs
pending rows and expired leases after recovery; the enrichment queue's unlimited
delivery retries no longer amplify these outages. Committed attempts retain the
four-claim cap. Terminal settlements keep a content-free reporting obligation;
recovery reports it through a CAS fence without repeating inference. Duplicate
wakes cannot emit another terminal outcome. Custody deferrals are nonterminal.

Nested TLS failures are classified before transport errors and remain terminal.
The HTTP diarizer immediately retries 408, 429 and 5xx once, then propagates the
typed error into the existing bounded speaker-only retry path. Other 4xx remain
terminal. This adds no slot waits, SDK retry loops, queue configuration changes,
full-enrichment replay or authority changes.

The sync GMP keep-list includes complete agreement, latency and owner-delta
histogram families alongside both final-pass counters. The historical metric
capture stays intact; missing source-backed names are declared separately.
Local tests use synthetic storage and HTTP transports, never production data.
