# C7: typed mobile events

JSON in `contracts/analytics/events.json` owns ids, exact wire names, property
shapes, lifecycle and consumer references. Run
`python3 scripts/check_event_registry.py --write`; commit generated Dart and
TRACKING_PLAN.md together. Four real, privacy-safe events are examples, not a
240-event migration. Product infra owns implementation. Nothing calls the new
throwing TypedEvents seam yet. No PlatformManager, adapter, consent, queue,
retry, identify or delivery changes belong here.

Generated sealed event classes accept only declared fields. Property keys are
Dart parameter names; each explicit wire_name preserves legacy spelling, including
underscores. SDK provenance keys cannot be event fields. The initial schema
admits booleans; subsequent batches may add bounded counts and generated closed
enums with rejection tests. Never accept arbitrary String, Map, Object, payload,
uid, hashed device address, transcript, memory text, email or exception text.
This is an allowlist, not a PII regex filter pretending to sanitize values.
C8 owns unadopted legacy events, including Memory Created/getTranscript statistics;
C7 makes no privacy claim for them. Unsafe events need reviewed replacements,
not byte-preserving migration. The pending emission oracle checks literal sink
payloads through both ready and pre-init queues; active constructor tests alone
prove only type safety. Oracle imports restrict the legacy manager to
AnalyticsManager: TypedEvents must resolve through the direct registry library,
not the manager’s convenience re-export.
The raw-call scanner checks known analytics receivers in adopted files. Aliases, dynamic dispatch and legacy manager methods can evade this
lexical tripwire; it is not data-flow proof. TypedEvents.emit alone may make one
AnalyticsManager().track call; direct SDK capture is forbidden there. Generated sealed
types provide the stronger boundary on the new API. Legacy person properties
and existing SDK identity are outside this change's privacy claim.

Implement TypedEvents.emit through existing AnalyticsManager.track, preserving
its no-key no-op, queue, consent and retry behavior. Do not send to the adapter
directly. Existing BuildProvenance registration supplies git_sha/build_number
(the SHA includes the dirty marker); do not add per-event copies. Cohort on
SDK `$app_namespace`, never a person channel. Test fixtures project that property
to SQL `app_namespace`. Signed-out emission is legitimate; an anonymous install,
a seeded backend principal and an authenticated app user are distinct. C7 does
not sign in the live session or introduce identity properties.

Every event references a checked-in consumer JSON with an owner, named question,
kind, event ids, query path and zero policy. The SQL query must execute against
synthetic rows and select the registered event in exactly the requested app
namespace/build, including empty and wrong-cohort controls. This example is a
named presence question, **not a claimed deployed dashboard or alert**. Dashboard,
alert or experiment adoption also records its real artifact URL in the consumer;
CI can validate the repository query, not external deployment. Presence queries
cannot prove a real emission occurred; each migrated feature keeps trigger tests
on every input/platform path. Particularly: iOS push-open needs an actual trigger,
a displayed rating is not feedback, and transport completion is not task success.

Wire name and property shape are immutable once committed. Deprecate, never
delete: keep the old row and its consumer query while released clients can emit
it. A rename adds a new id plus replaced_by on the old row, with a consumer query
that explicitly combines or separates both names and deduplicates overlapping
emissions. Do not dual-emit implicitly. This contract does not authorize deleting
historical names on a time cutoff; a consumer migration review must first account
for historical queries and C10's support window.

F1 owns intent vocabulary and success semantics. EventPhase and EventCorrelation
reserve point/attempt/outcome and an opaque, randomly minted attempt id (never
identity-derived). Schema phase/intent/correlation fields are reserved; C7 admits only legacy
point events and adds no correlation properties. F1's reviewed schema extension
must require one shared correlation per attempt/outcome and test terminal counts
before those phases become emit-capable. The reserved correlation descriptor is
`{type: random_attempt_id, field: correlation_id}`; point rows keep it null. C3's shared recordFallback remains the
single fallback helper; register fallback_triggered with its existing closed
fields later, without inventing mobile_reason or a second helper.

Migrate one feature batch, roughly 5–15 safe events per PR. Before editing a
legacy method, pin adapter emission goldens from the pre-migration commit and
record its SHA. Invoke every migrated trigger with all enum/bool branches and
optional-field absence; compare ordered event names and property keys/values,
including types and omitted nulls, at the recording adapter. The protected C7
example executes both APIs through the actual queue and checks literal names;
each batch must retain independent pre-migration goldens so editing both paths
cannot hide drift. Add a file to adopted_files only when every emission in it is
migrated and trigger coverage exists. No regression after adoption; unadopted files (including new ones) stay free. Do not mark the 2,226-line manager adopted piecemeal.
