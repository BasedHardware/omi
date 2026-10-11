# Why a Get Started colour change reloads 387 libraries

Workstream C. Static import-graph analysis of `package:omi` (`app/lib`) on
`origin/main` (`b0f8455e35`). No app code changed. No device boot.

Harness trigger: signed-out **Get Started** button colour
(`backgroundColor: Colors.black` on the `ElevatedButton` in
`app/lib/pages/onboarding/device_selection.dart`). Measured warm reload:
**387 of 4032** libraries, every save after the first. First save is 469;
that extra 82 is lazy libraries entering the isolate once and is not this
graph.

## What 387 is

Dart's incremental compiler invalidates the changed library and every
library that **imports it, transitively** (reverse closure). On this graph
that set is **exactly 387** `package:omi` libraries. 4032 is the whole
isolate (dart SDK + Flutter + plugins + app). l10n locale files are not in
the 387: they import nothing in the app.

Genuine direct dependent of the colour leaf: **one file**,
`app/lib/mobile/mobile_app.dart`. The other 386 only appear because they transit a
hub. The leaf sits in a **378-library strongly connected component** with
`HomePage`. A chat-chip edit, a home edit, and this splash edit all
invalidate the same 387.

```
device_selection.dart          ← colour leaf
  ↑ imported by
mobile_app.dart
  ↑ imported by
app_shell.dart
  ↑ imported by (back-edges)
settings_drawer.dart  and  delete_account.dart
  ↑ (drawer ← home; delete_account ← profile ← drawer)
pages/home/page.dart           ← god file, 62 outbound imports
  ↑ imported by 8 descendants (and by mobile_app, correctly)
everyone who can reach those descendants
```

The back-edges exist to run `routeToPage(context, const AppShell(), replace: true)`
after sign-out / delete. `app/lib/pages/settings/settings_drawer.dart` also reaches `AppShell`
indirectly (`drawer → profile → delete_account → app_shell`), so cutting
only the direct `settings_drawer → app_shell` import saves **0**.

Reverse-set mix: 172 pages, 96 services, 34 backend, 27 utils, 27
providers, 18 widgets. High fan-in files (`l10n_extensions` 204,
`logger` 162, `platform_manager` 110, `preferences` 103) are widely
imported, but they are not what *amplifies this leaf*. Changing them is as
bad or worse; splitting them does not shrink a Get Started reload.

Barrels (`app/lib/backend/schema/schema.dart`, `app/lib/services/wals.dart`) and
`app/lib/gen/assets.gen.dart` are the same: high fan-in, not the cycle.

## Ranked edges

Before: **387** invalidated `package:omi` libraries for the Get Started
colour edit. “After” is the reverse closure with that edge (or pair)
removed. Typical leaf is `app/lib/pages/chat/widgets/chat_followup_chip.dart`.

| Rank | Edge | Get Started after (save) | Chat-chip after (save) | Load-bearing? |
| --- | --- | --- | --- | --- |
| 1 | **Both** `settings_drawer.dart → app_shell.dart` **and** `delete_account.dart → app_shell.dart` | **4 (−383)** | 387 (0) | **No as types.** They only construct `AppShell` to restart the tree. Inject a restart callback from `main` / `AppShell`. Remaining 4: `device_selection`, `mobile_app`, `app_shell`, `main`. |
| 2 | Descendant → `app/lib/pages/home/page.dart` imports (eight when measured; the old speech-profile page has since been deleted): `app/lib/pages/conversation_detail/page.dart`, `app/lib/pages/onboarding/wrapper.dart`, `app/lib/services/notifications.dart`, `app/lib/pages/home/firmware_update.dart`, `app/lib/pages/home/omiglass_ota_update.dart`, `app/lib/pages/onboarding/permissions/permissions_checker.dart`, `app/lib/pages/capture/connect.dart`. Keep `mobile_app → home`. | 8 (−379) | **59 (−328)** | **Partially.** They import `HomePage` to `routeToPage` back to home. The route registry (B1) is the replacement. This is the typical-leaf lever; (1) is not. |
| 3 | `home/page.dart → settings_drawer.dart` | 7 (−380) | (not the real cut) | **Yes.** Parent composing a child. Looks like a lever only because the drawer is on the back-edge path. Do not remove. |
| 4 | `app_shell.dart → mobile_app.dart` | 2 (−385) | (not the real cut) | **Yes.** Parent composing a child. Do not remove. |
| 5 | `device_selection.dart → wrapper.dart` | 387 (0 reverse); forward 596 → 53 | 387 (0) | Navigation to onboarding. Invert with a builder from `MobileApp` if you want a cheaper *forward* graph. **Does not move the measured 387.** |
| 6 | `wrapper.dart → home/page.dart` | 387 (0) | 387 (0) | Other wrapper children already import home (`permissions_checker`). Cutting this edge alone does nothing. Covered by (2). |

Single-edge cuts that look tempting and save **zero** on this trigger:
`settings_drawer → app_shell` alone (profile/delete_account still closes the
cycle), `wrapper → home`, `mobile_app → home`, `mobile_app → wrapper`,
schema/wals barrels, `l10n_extensions → app_localizations` (48 locales are
forward-only).

## Is 387 the floor?

**For this Get Started trigger: no.** The 387 is the AppShell-restart
cycle, not an irreducible graph. Rank 1 should drop the warm invalidation
set from 387 to 4 omi libraries. If reload cost tracks that set, Android
warm 2.9–3.8 s for *this* edit has room under 3 s on this route.

**For a typical in-app widget edit: 387 is near the floor until rank 2.**
A chat-chip change stays at 387 after rank 1. Rank 2 drops it to 59, not
to 4 — widgets still import `app/lib/pages/conversation_detail/page.dart` to open a
conversation, which is a second navigation hub. Further cuts there are
the same shape (route registry instead of importing a page) and were not
needed to explain the harness number.

The graph is not “everything imports everything” through a barrel. It is
one SCC held by a handful of ancestor-importing-descendant back-edges.
Do not extract the Get Started colour into a shared theme file: that
cannot shrink this set and can grow it.

## How this was counted

Walk `import` / `export` of every `app/lib/**/*.dart` library
(`part` files merged into their parent). Ignore `dart:` and other
packages. Reverse BFS from the changed library = predicted warm
invalidation set. 618 omi libraries exist; 387 of them import the splash
page transitively; 378 are in its SCC.
