# Omi iOS v2 — interaction spec (what every button does, how every screen changes)

This folder is the build map for the native app. The designs show **what it looks like**; this spec says **what each
control does in production, where it goes, and how the screen changes**, using only existing backend contracts.

| File | Contents |
|---|---|
| `README.md` | This page: vocabulary, app-wide navigation, motion and gesture rules, coming-back rules, how to use the spec |
| `INDEX.md` | Every screen: plan IDs, build stage, presentation, number of controls, which file |
| `NAVIGATION.md` | Every link between screens (from → control → to → transition), generated |
| `screens/01-launch-onboarding.md` | Startup, Gate, Welcome, Sign in, onboarding steps 1–8 (incl. Choose a plan), Complete |
| `screens/02-device-tutorial-sync.md` | Tutorial T01–T05, Pairing, Discover, Device, Firmware, Offline recordings |
| `screens/03-home-capture-conversations.md` | Home (+ first day), Live, Processing, Conversation, Speaker, Conversations (+ menu, offline), Search, Recap, Share card |
| `screens/04-tasks-chat-memories.md` | Tasks, Edit task, Ask Omi, Voice mode, Memories, Memory, Graph |
| `screens/05-apps-calls-settings.md` | Apps, App detail, Integrations, Call, Settings and all settings pages, Plans, Delete account |
| `screens/06-system-surfaces.md` | Lock Screen Live Activity, widgets (proposed, on-device only) |
| `generate.py`, `content_*.py` | Source of the screen files. Controls are read from the designs; behaviour text lives in `content_*.py` |

Regenerate after any design or behaviour change:
`./generator/build_all.sh && python3 spec/generate.py` (fails if any control has no behaviour, or a file exceeds 1,300 lines).

## How to read a screen entry

Each screen has: plan IDs · build stage (S00–S14 from the implementation plan) · how it is presented · purpose ·
reached from (generated) · **data: the exact existing endpoints** (as used by the Flutter app, `app/lib/backend/http/api/*.dart`) ·
layout order · states · **a table of every interactive element in the design** · controls required but not drawn ·
gestures and motion · rules.

Controls table columns:

- **Control** — the label or VoiceOver name. `‹dynamic›` = text that comes from state.
- **Shown when** — the state condition from the design (`always`, `isSummary`, `selecting`, `each row`…).
- **Production behaviour** — what the real app does, including the endpoint, validation and failure handling.
- **Goes to** — destination screen, or `—` if it acts in place.
- **Transition** — from the vocabulary below.

Sample names, numbers and `[Price]` are placeholders, never production copy. Rows repeated in the design (lists)
are one row per data item in production.

## Vocabulary

| Presentation | SwiftUI | Used for |
|---|---|---|
| tab root | `TabView` selection + one `NavigationStack` per tab | Home, Conversations, Tasks, Apps |
| push | `NavigationStack` push | drilling into something (conversation, memory, app, settings page) |
| sheet (large / medium) | `.sheet` + detents (`UISheetPresentationController` on iOS 15) | a task on top of where you are: Settings, Edit task, Plans, Tag speaker, Pairing, Device |
| full-screen cover | `.fullScreenCover`, matched geometry from its source card | Live, Processing, Voice mode, Call, tutorial |
| context menu | `.contextMenu` with preview | long-press on rows |
| system | Apple UI: permission prompts, share sheet, Safari view, `ASWebAuthenticationSession`, document/photo pickers | never rebuilt |
| system alert | `.alert` / `.confirmationDialog` | only decisions that lose data or cost money |
| replace root | swap the root view (cross-fade 0.3 s) | launch → onboarding → app, sign-out, account deletion |

| Transition | Motion (see the Motion map board) | Reverse |
|---|---|---|
| push | new screen from the right, old drifts 30% left and dims · 0.5 s spring | pop: back button or edge swipe, tracks the finger 1:1 |
| sheet | sheet rises; presenting screen scales to 92% and dims | dismiss: close/Done or drag the grabber down (release past 25% or flick) |
| cover | source card grows into the full screen (corners, pendant, timer travel with it) · 0.55 s | uncover: shrinks back into the card; swipe down on the header |
| tab | content cross-fades 0.2 s, the glass pill glides 0.4 s; each tab keeps its stack and scroll | — |
| in place | state change on the same screen (segment, toggle, menu, row expand) | — |

Springs: default (response 0.4, damping 0.85) for navigation and cards; snappy (0.3, 0.9) for toggles, segments, press;
gentle (0.6, 1.0) for arriving content; bouncy (0.45, 0.7) only for success (check, star, plan picked).
Reduce Motion: slides become 0.2 s fades, loops stop, gestures still work.

## App-wide rules

**Navigation shell.** Four tabs (Home, Conversations, Tasks, Apps) in a floating glass bar, plus a separate round
**Ask Omi** button that **pushes Chat onto the current tab's stack** (Chat is not a tab). Pushed detail screens and
sheets do not show the tab bar. Re-tapping the active tab pops to its root, then scrolls to top.
Settings is a large sheet from Home's account button; Device/Pairing are sheets from the status pill.

**Launch.** Keychain session → cached Home immediately → refresh in place. Signed out → Welcome. Onboarding
incomplete (`GET v1/users/onboarding`) → the next onboarding step. Update/migration required → Gate. Only a failed
bootstrap shows Startup.

**Onboarding stack (8 steps).** Consent → Name → Language → Source → Permissions → Voice (+ Review) → What Omi
knows → Choose a plan → Complete. Progress bar fills 0.45 s per step. Back always works. Skippable steps: Source,
Voice, Choose a plan (Free). Completion is written to the server (`PATCH v1/users/onboarding {completed:true}`)
before the app opens.

**Purchases.** The existing app sells Plus/Unlimited through **Stripe Checkout** (`POST v1/payments/checkout-session`,
opened in a web session), manages via the Stripe customer portal, and does **not** use StoreKit. There is no
Restore Purchases. Prices always come from `GET v1/payments/available-plans`.

**Truthful status.** Pendant connection, audio flowing, saved on iPhone, uploaded, processed, summary ready are
separate states with separate labels. Blue (LED colour) appears only while audio is really being captured.

**Writes.** A control that changes server state shows the new value only after the server accepts it (or shows
it optimistically **with** rollback + toast on failure, where marked). Repeated taps = one operation. Mutations
keep the user's draft on failure.

**Destructive actions.** System alert first. Toast with Undo only when the server can actually undo.

**Empty vs failed.** Every list distinguishes true empty, failed (retry row), offline (cached + banner) and
partial (valid rows + “some items couldn't load”).

## Gestures used across the app

| Gesture | Where | Result |
|---|---|---|
| Edge swipe right | every pushed screen | back |
| Drag grabber down | every sheet | dismiss (unsaved edits → confirmation) |
| Swipe down on header | Live, Voice mode, Call | uncover back into the source card |
| Pull to refresh | Home, Conversations, Tasks, Memories | refresh; Home/Conversations also ask the pendant for offline audio |
| Swipe left on row | Conversations, Memories, Tasks, installed Apps | actions (Star/Delete, Archive/Delete, Snooze/Delete); full swipe = last action + toast |
| Swipe right on row | Tasks | complete (success tick at threshold) |
| Long-press row | conversations, memories, tasks, apps | context menu with preview |
| Long-press + drag | Tasks, app order | reorder |
| Scrub waveform | Conversation audio | seek; transcript follows |
| Swipe between pages | Daily recap days | previous/next day |
| Tap active tab | any tab | pop to root, then scroll to top |
| Pendant single press | anywhere | voice question (Ask) |
| Pendant double-press | anywhere | local setting `doubleTapAction`: 0 end conversation (default), 1 mute/unmute, 2 star |

Every gesture has a visible equivalent (button or menu item) for VoiceOver and Switch Control.

## Coming back to the app

| Situation | What the user sees |
|---|---|
| Back within ~10 minutes | Nothing moves: same tab, scroll, open sheet, draft. Updates slot in silently. |
| Back after the pendant recorded offline | Home: sync card rises and fills with real progress; each finished conversation drops into the list; card folds away. |
| Back while recording (icon, Island, Live Activity) | The Island/Live Activity grows into Home's Live card; one clock, so the timer never jumps. |
| From a notification | Home first, then the target pushes on top; Back lands on Home, never outside the app. |
| First open of a new day | Greeting cross-fades; yesterday's recap card settles in at the top. |
| Cold launch | Omi mark (LED on) travels into the status pill while cached Home fills in; no spinner longer than the work. |
| Signed out elsewhere / token revoked | Stop protected work, hide account data, show Sign in; recordings stay bound to their account on disk. |

## Using this with the implementation plan

For each screen in a stage: open its entry here + the render + the geometry file, build every row of its
controls table (or mark it explicitly disabled/unavailable with the reason), then verify states and gestures.
A screen is **not done** while any row in its table is unimplemented and unmarked.
