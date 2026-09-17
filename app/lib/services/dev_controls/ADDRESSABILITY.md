# B1: address existing screens, preserve navigation

Builder: App UI after [B0](REGISTRATION.md). Skeleton only; no bootstrap hook.
Migrate chat first (existing input/send keys and j2 oracle), then home,
conversations, conversation detail, memories, tasks, settings, onboarding, devices.
The spine leaves hot-file hooks to the builder. No router migration.

## One catalog, bounded acceptance

`app/contracts/addressability/catalog.json` owns routes, keys, required controls,
and the interactive constructor/callback vocabulary. Run
`python3 scripts/check_app_addressability.py --generate` for Dart constants and
the widget predicate; host tooling reads JSON. Generated drift fails the check.

Initial scope is **15 controls**, not nine directories of accessibility debt:

| Surface | Count | Controls |
| --- | ---: | --- |
| chat | 2 | message input, send |
| home | 3 | home tab, conversations tab, tasks tab |
| conversations | 1 | seeded conversation row |
| conversation_detail | 2 | back, ask about conversation |
| memories | 1 | create memory |
| tasks | 1 | create action item |
| settings | 2 | profile, done |
| onboarding | 1 | Google sign-in |
| devices | 2 | back, connection guide |

These are initial entry-state handles, not complete workflows. Add a control when
a reviewed journey/agent task needs it: add key, source, scope, English label,
role/action and fixture scenario to the catalog; implement localized semantics;
add an interaction assertion. New states need a separate scenario test. Never
remove a catalog obligation to pass a surface. Dynamic row entries identify the
synthetic fixture record; production keys derive from each actual record; row labels include its human title.

Keys use `omi.<surface>.<control>[.<qualifier>]`: lower snake case surface/control,
qualifier `[a-z0-9][a-z0-9_-]*`. `AddressKey.row(surface,id)` is
`omi.<surface>.row.r` + all 64 lowercase SHA256(UTF8 opaque id) hex characters.
Reject empty/>256-byte IDs and unknown surfaces. Never use position, email or text.
A root/layout needs only a key. **Catalogued controls** require that key on the
actual interactive widget, matching Semantics identifier, localized human label,
real role/enabled/selected state and standard accessibility action parity with
touch, in every build. No `omi.*` or fixture IDs spoken; merge decoration and
avoid duplicate focus stops. `label_en` pins the English fixture, not production
hardcoded English. Other controls retain normal accessibility standards and the
no-growth ratchet, but are not B1's acceptance scope. Device VoiceOver/TalkBack
review remains separate from widget evidence.

## Existing owners and transitions

`AppAddressability` adapts the existing Navigator, HomeProvider and providers.
Home uses lazy IndexedStack slots 0/1/2; pushed pages use existing constructors;
settings uses SettingsDrawer.show. Put `OmiKeys.homeRoot` on a stable
KeyedSubtree **inside slot 0**, wrapping HomeContentPage; retain its existing
GlobalKey on HomeContentPage itself. The same applies to other tab roots. A key
on the whole shell would incorrectly remain visible on every tab. Shell-scoped
catalog controls (bottom bar) stay outside the tab root. Wrapping is allowed;
replacing GlobalKeys or discarding cached tabs is not.

`buildShell(initialRoute: 'home')` returns the real signed-in shell.
`buildShell(initialRoute: 'onboarding')` returns the real OnboardingWrapper with
the signed-out fixture; never construct HomePage first. `navigate('onboarding')`
from a signed-in shell refuses `auth-required`; navigation never signs out.
Real sign-out uses the existing auth owner to replace the shell. During auth
cutover/navigation, visibleRoute is null and routed is false; publish onboarding
only after signed-out auth and its root are ready. Signing in follows the same rule.

Admission checks eligibility/owner first, then route/auth/record. Refusal codes:
ineligible, unmounted, unknown-route, auth-required, record-required,
record-unavailable, busy. All refusals are **failed Futures**, never synchronous
throws. Reserve the mutation slot synchronously before the first await; a second
call returns a failed busy Future without interleaving. Navigate completes at
visible-root readiness, not route pop. Fetch detail through the real provider/API
and check fixture ownership; foreign/missing records cannot open placeholder pages.

Eligible bootstrap connects the adapter to the existing navigator/provider scope.
An observer plus tab/sheet completion maintains visibleRoute. Fixtures replace
external auth/plugin/BLE I/O only (including host platform detection); providers and navigation remain real.
JourneyHermeticBoot uses harness `mobile/v1.json` identity and JourneyFixtureBackend:
j1's seeded detail, empty chat/memories/tasks, signed-out onboarding. Surface tests
exercise registered VM handlers, actual page Types, roots, controls and transitions
on iOS/Android widget targets. Cached tabs must disappear from onstage finders,
remain in all-element finders, and retain element identity on return.

## semantic-controls/v2

Keep B0's five extensions. Omitted version selects v1; explicit
`semantic-controls/v2` selects v2; unknown version refuses unsupported-version.
v2 navigate accepts destination=registry id plus optional record_id; returns
`{ok:true}` after readiness. Errors are bounded extension errors. No generic
action: keys establish neither permission nor safe side effects.

`state` returns the snapshot object directly, with **no envelope**. Exact example:

```json
{"contract_version":"semantic-controls/v2","route":"chat","auth":"signedIn","capture":"idle","ble":"disconnected","wal":"ready","wal_pending":3,"providers":{"messages":"ready","conversations":"unavailable","memories":"unavailable","tasks":"unavailable"},"flags":[{"id":"voice","effective":false,"override":null}],"flags_hydrated":true,"readiness":{"signedIn":true,"routed":true,"captureIdle":true,"appReady":true}}
```

Use enum `.name` spelling from addressability.dart; route is registry id/null,
never a path. Surface wire equality compares this JSON-decoded map to snapshot().
Schema: `semantic-controls-v2.schema.json`; exact projection oracle:
`b1_controls_test.dart`. WAL count saturates at 1000, unavailable => null.
Flags are sorted unique registered IDs, max64, effective bool/override nullable
bool; Spine B owns policy. No transcripts, memories, identity, device addresses,
preferences, timestamps, exceptions or arbitrary provider maps. Missing providers
are unavailable; unknown visible routes project null. Reject invalid counts/IDs.

Readiness: signedIn, routed (registered visible root, no transition), captureIdle
(known idle); appReady requires all three plus WAL ready, BLE known/not connecting,
flags hydrated and active route's required provider ready. waitReady polls fresh
state, rejects unknown predicates/nonpositive/>30s deadlines, and times out typed.
Capabilities list actual extensions, versions, implemented routes and predicates.
Guard remains debug + local_dev + OMI_DEV_CONTROLS=1; existing guard tests govern.
B1 alone does not enable V1 live journey attachment.

## Honest enforcement

The lexical checker cannot distinguish screens from helpers/dialogs. Page-file,
class-name and navigation-count inventories are removed. New addressable screens
must declare `// omi-route: id` beside their class and register it; changed-file
checks catch undeclared registry IDs, **not unmarked new screens**. Review catches
omitted declarations. No whole-tree source walk on ordinary contributor diffs.

Changed files retain min(baseline, base-source) unkeyed debt limits; baseline stays
unchanged. Constructor/callback names come from the same catalog as widget tests.
Static callback presence conservatively counts disabled callbacks; runtime checks
can include disabled controls. Aliases/custom wrappers escape; per-file debt swaps
can escape. No analyzer dependency. `--surface` checks only catalog declarations/
references; widget contracts prove placement, semantics and reachability. It never
zeroes directory debt. Complete both platform scenarios before retiring a marker.
