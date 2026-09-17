# B1: address existing screens, preserve their navigation

Builder: App UI, after [B0](REGISTRATION.md). This is a skeleton; no bootstrap
hook is installed. Implement chat first (existing input/send keys and j2 oracle),
then home, conversations, conversation detail, memories, tasks, settings,
onboarding, devices. Each surface removes its own pending marker only after
both platform variants pass. The spine does not edit the hot files.

## Keys and accessibility

`app/contracts/addressability/catalog.json` is the source for routes and static
keys. `python3 scripts/check_app_addressability.py --generate` emits Dart
`OmiKeys`; the check rejects drift. Host tools read the same JSON. Grammar:
`omi.<surface>.<control>[.<qualifier>]`; lower snake case surface/control,
qualifier `[a-z0-9][a-z0-9_-]*`. Dynamic rows use `AddressKey.row(surface,id)`:
`omi.<surface>.row.r` + SHA256(UTF8 opaque backend id), all 64 lowercase hex
characters. Reject empty/>256-byte ids and unknown surfaces. Never list index,
text, email, transcript, or position. Sorting must not change a row's key.
Static keys must be unique within the visible route; lists may reuse control
names only under distinct row keys. Preserve stateful GlobalKeys; put the root
ValueKey on a wrapper instead of replacing those handles.

A Key alone suffices for noninteractive roots/layout. Each focusable/actionable
control also needs a Semantics identifier equal to its key, a localized human
label, its real role, enabled/selected state, and the same standard accessibility
actions as touch. This applies in **every build**, including physical profile
builds without a VM service. Do not speak `omi.*` or fixture IDs as labels.
Merge decorative icons; avoid duplicate focus stops. Protected surface tests
inspect real semantics actions, nonempty human labels, identifiers and unique
visible keys on iOS/Android target platforms; chat pins the English labels
`Message` and `Send message`. The builder adds corresponding translations through
App UI's normal localization path. Widget tests do not replace device VoiceOver/
TalkBack review, which must be reported separately.

## Registry and production hooks

`routes` contains the nine intended addressable destinations, with source class,
root, reach method, fixture and auth/profile preconditions. Entries are promises,
not proof of readiness: capabilities advertise only routes whose implementation
is ready. `deferred_pages` inventories existing other page/helper files as
**unaddressable**; it is not a walker target. New page files must have a route
entry (split non-screen helpers outside pages). `navigation_sites` inventories navigation calls per file. Existing sites have
frozen legacy IDs; each added call must reference a real route ID, never another
legacy entry. Additions to deferred_pages are rejected after this baseline.
The check is a static inventory, not proof that computed destinations execute.

Do not migrate routers. `AppAddressability` is the sole production adapter.
Home uses HomeProvider.selectedIndex and the existing lazy IndexedStack slots
0/1/2; chat/memories/detail/devices use the same page constructors and Navigator
push path as their UI; settings calls SettingsDrawer.show. Onboarding opens its
existing wrapper with signed-out fixture state. Preserve back/pop behavior and
refuse unknown routes, unmet auth, nonlocal profile, missing/foreign record id,
concurrent navigation and unmounted owners before changing the stack. Refusals
are AddressabilityRefused codes: ineligible, unmounted, unknown-route,
auth-required, record-required, record-unavailable, busy. Admission order starts
with eligibility/owner; no navigation mutation or content-bearing error on refusal.
Navigate completes after the visible root is ready, not after that route pops. A detail
record is fetched through the real provider/API and checked for fixture ownership;
never construct an empty page to pretend a destination exists.

Builder hooks: eligible main bootstrap connects the adapter to the existing
navigator/provider scope; home exports tab selection through its existing owner;
pages mount catalog root keys and accessible controls; a NavigatorObserver plus
tab/sheet completion updates visible route. Mounted offstage tabs are not visible
routes. `buildShell()` returns the actual HomePage shell used by the adapter;
protected tests pump it via JourneyHermeticBoot, never a second test-only table.
The fixture catalog binds identity to harness `mobile/v1.json` and data to
JourneyFixtureBackend: conversation-one uses j1's exact id, chat/memories begin
empty, other signed-in surfaces use empty data, onboarding uses no principal.
The fixture helper returns additional real auth/capture/device/memories/tasks/
onboarding providers to JourneyHermeticBoot. External plugin/auth/BLE I/O may
be faked; route decisions/providers stay real. No duplicate production bootstrap.

## semantic-controls/v2

Keep the five B0 extension names. An omitted `version` wire parameter negotiates v1; explicit
`semantic-controls/v2` selects v2; any other version returns unsupported-version.
Never silently downgrade. v2 navigate takes `destination` (registry id) and
optional `record_id`, returning `{ok:true}` only after readiness; refusals are
service-extension errors with bounded codes, never successful no-ops. v1's existing state contract stays available to the
V1 broker; in-tree new consumers request v2 explicitly. Capabilities are exact
registered suffixes, supported_versions, selected contract_version, routes,
and readiness names. **No generic action** in B1: a key alone establishes neither
permission nor safe side effects. UI/accessibility remains the action channel.

The v2 snapshot has only: version, route (id/null), auth/capture/ble/wal enum
states, wal_pending (0..1000 saturated; unavailable WAL => null), providers
(`messages`, `conversations`, `memories`, `tasks`: LoadPhase), flags (sorted
registered id/effective/override booleans, max 64; unique IDs matching
`[a-z][a-z0-9_]{0,47}`), flags_hydrated and readiness.
No uid/email, device names/addresses, recording IDs, text, timestamps, exceptions,
preferences or arbitrary maps. Missing providers are unavailable, never ready; an unregistered visible route
projects null rather than echoing an arbitrary route string.
Reject negative counts, unknown provider/flag IDs and >64 flags. The typed
ControlStateSource is a read-only seam over AuthenticationProvider, CaptureProvider,
DeviceProvider, capture-owned WAL, Message/Conversation/Memory/ActionItem providers.
Spine B owns flag registration and override policy; B1 only reads FlagState.

Readiness predicates: signedIn, routed (visible registered root mounted, no
transition), captureIdle (known idle), appReady (all three, WAL ready, BLE not
unavailable/connecting, flags hydrated, active route's required provider ready).
Never infer state from navigator.mounted alone or catch errors into readiness.
waitReady rejects unknown predicates and nonpositive/>30s deadlines, polls boundedly,
returns a fresh snapshot or a typed timeout, and rechecks across navigation/auth
cutover. VM install remains debug + local_dev + OMI_DEV_CONTROLS=1; the existing
guard test remains authoritative. Pure projection types grant no VM access.

## Enforcement and per-surface done

`check_app_addressability.py` runs in local/CI manifest lanes. It tokenizes Dart,
balances constructor arguments, and counts the named interactive constructors
in its INTERACTIVE set; a child's key cannot cover its parent. Only changed
files are held to min(committed baseline, base revision count). No-growth is
per-file, so replacement of one debt item by another can escape. Custom wrappers,
aliased constructors and computed route factories can escape; disabled controls
and gesture-only detectors can be conservative positives. Review those cases;
do not claim analyzer precision. This adds no plugin/dependency to the Dart job.

`b1_*_surface_test.dart` + `b1_surface_contract.dart` is the executable template, instantiated for all nine
routes on iOS and Android. It uses the real adapter/shell, checks actual page
Type + enclosing root, state through actual registered v2 handlers (equal to
the live projection), unique keys and semantics, then a real
back/tab transition. Duplicate/offstage roots, fake registry-only navigation,
and identifier-only Semantics fail. Builder adds scenario-specific coverage and
zeroes that surface's static debt before removing the marker. Unit contracts
also pin key stability, privacy projection, readiness and negotiation.
Live verify still needs a separate executable journey adapter; B1 alone does
not enable V1 `fast --session`. No router, flags, singleton or HTTP migration here.
