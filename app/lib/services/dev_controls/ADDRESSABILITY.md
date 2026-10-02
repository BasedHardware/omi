# B1: address existing screens, preserve navigation

Builder: App UI after [B0](REGISTRATION.md).
Migrate chat first, then settings, devices, memories, conversations, onboarding
auth, tasks, home tabs (bottom_nav_bar.dart), and conversation detail last.
Builder owns hot-file hooks; no router migration.

## One catalog, bounded acceptance

`app/contracts/addressability/catalog.json` owns routes, keys, required controls,
and the interactive constructor/callback vocabulary. Run
`python3 scripts/check_app_addressability.py --generate` for Dart constants and
the widget predicate; host tooling reads JSON. Generated drift fails.

Initial scope is **17 distinct controls**, not nine directories of accessibility debt:

| Surface | Count | Controls |
| --- | ---: | --- |
| chat | 2 | message input, send |
| home | 4 | home, conversations, tasks, apps tabs |
| conversations | 1 | seeded conversation row |
| conversation_detail | 2 | back, ask about conversation |
| memories | 1 | create memory |
| tasks | 1 | create action item |
| settings | 2 | profile, done |
| onboarding | 2 | Google sign-in, separate local-dev sign-in |
| devices | 2 | back, connection guide |

Add controls only for reviewed journey/agent needs: catalog key/source/scope/ARB
reference/role/action/scenario, localized semantics and interaction assertion.
New states need scenario tests; never delete obligations to pass. Dynamic row entries identify the
synthetic fixture record; production keys derive from conversation.id, never conversationIdx. Row labels
use the record’s human title. Keys are unique within the visible route/root, not
across offstage cached tabs; host lookups must supply route and scope.

Keys use `omi.<surface>.<control>[.<qualifier>]`: lower snake case surface/control,
qualifier `[a-z0-9][a-z0-9_-]*`. `AddressKey.row(surface,id)` is
`omi.<surface>.row.r` + all 64 lowercase SHA256(UTF8 opaque id) hex characters.
Reject empty/>256-byte IDs and unknown surfaces. Never use position, email or text.
Roots need keys. Catalogued interactive widgets need matching Semantics identifiers,
localized labels, real role/enabled/selected state and touch/action parity in every build. No `omi.*` or fixture IDs spoken; merge decoration and
avoid duplicate focus stops. ARB is the sole label authority: replace starter label_en with label_arb (an ARB
key, no copied text). Row labels instead use the actual record title; label_arb
is null. The revised template checks rendered labels against those sources.
Builder updates catalog/schema/generator/checker together; never add English
fallbacks to satisfy old starter data. Other controls retain normal accessibility standards and the ratchet. Device accessibility review remains separate.

## Existing owners and transitions

`AppAddressability` adapts the existing Navigator, HomeProvider and providers.
Home uses lazy IndexedStack slots 0/1/2/3 (home/conversations/tasks/apps); pushed pages use existing constructors;
settings uses SettingsDrawer.show. Put `OmiKeys.homeRoot` on a stable
KeyedSubtree **inside slot 0**, wrapping HomeContentPage; retain its existing
GlobalKey on HomeContentPage itself. Likewise for other tabs. A key
on the whole shell would incorrectly remain visible on every tab. Shell controls stay outside the tab root. Add apps route/root for slot3; its
entry control is the existing apps tab (shared with home’s catalog). Home’s
contract reaches the real AppsPage; app-store feature controls are out of scope. Wrap; retain GlobalKeys and cached tabs.

`buildShell(initialRoute: 'home')` returns the real signed-in shell.
`buildShell(initialRoute: 'onboarding')` returns the real OnboardingWrapper with
the signed-out fixture; never construct HomePage first. `navigate('onboarding')`
from a signed-in shell refuses `auth-required`; navigation never signs out.
Real sign-out uses the existing auth owner to replace the shell. During auth
cutover/navigation, visibleRoute is null and routed is false; publish onboarding
only after signed-out auth and its root are ready. Signing in follows the same rule. Local-dev sign-in calls onLocalDevSignIn,
not Google OAuth; add omi.onboarding.local_dev with ARB localDevSignIn.
The fixture replaces auth I/O and host-platform detection, not the auth owner.
TargetPlatform alone does not change dart:io Platform. LIVE_SIGNIN’s UID-only
control is separate; this catalog does not make Google sign-in mint local tokens.

Admission checks eligibility/owner first, then route/auth/record. Refusal codes:
ineligible, unmounted, unknown-route, auth-required, record-required,
record-unavailable, busy. All refusals are **failed Futures**, never synchronous
throws. Reserve the mutation slot synchronously before the first await; a second
call returns a failed busy Future without interleaving. Navigate completes at
visible-root readiness, not route pop. Fetch detail through the real provider/API
and check fixture ownership; foreign/missing records cannot open placeholder pages.

Eligible bootstrap connects the adapter to the existing navigator/provider scope.
Observe tab/sheet completion for visibleRoute. Fixtures replace external I/O,
not providers or navigation.
Surface tests
exercise registered VM handlers, actual page Types, roots, controls and transitions
on iOS/Android widget targets. Cached tabs must disappear from onstage finders,
retain element identity offstage and on return. Release semantics handles in
`finally`; binding invariants precede `addTearDown`. Never delay teardown to hide timers.
Dismissal must pop the actual route, complete its reverse transition, and dispose
the page. Pump frames until that route’s `completed`, bounded by its declared
reverse duration plus 1s; do not wait for unrelated animations to settle. A single
1s pump starts an idle ticker at elapsed zero; it does not finish the animation.

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
V1 live journeys remain unsupported.

## Honest enforcement

The lexical checker cannot distinguish screens from helpers/dialogs. New addressable screens
must declare `// omi-route: id` beside their class and register it; changed-file
checks catch undeclared registry IDs, **not unmarked new screens**. Review catches
omitted declarations. No whole-tree source walk on ordinary contributor diffs.

Ratchet adoption follows PENDING_CONTRACTS.md and adopted-files.json. The shared
constructor vocabulary counts disabled callbacks; aliases/wrappers and debt swaps
can escape. --surface checks catalog references, never directory-wide zero debt.
Both platform scenarios must pass before marker retirement.
