# TODOS — app-v2

Deferred work captured during planning. Add to a sprint when picking up.

## Register v2 Firebase bundle IDs (one-time, user action)

**What:** Register `com.togodynamics.nootoV2` in the `nooto-dev` Firebase project (iOS + Android), download the platform config files, then run `flutterfire configure --project=nooto-dev` from `app-v2/` to overwrite `lib/firebase_options.dart` with real values. After that, flip `kEnableFirebaseAuth` to `true` in `lib/env_flags.dart`.

**Why:** PR2a ships the auth-gated boot path, the v2 `ApiClient`, and a placeholder `firebase_options.dart` that throws `UnimplementedError` if invoked. Real Firebase init needs the v2 bundle registered in console first — this is the gating step before PR2b/c can run against the real backend.

**Steps:**
1. Firebase console → `nooto-dev` project → Project settings → Your apps → Add iOS app with bundle `com.togodynamics.nootoV2`. Download `GoogleService-Info.plist` and drop into `app-v2/ios/Runner/`.
2. Same console → Add Android app with package `com.togodynamics.nootoV2`. Download `google-services.json` and drop into `app-v2/android/app/`.
3. From `app-v2/` run: `flutterfire configure --project=nooto-dev`. The wizard regenerates `lib/firebase_options.dart` with real platform values.
4. Edit `lib/env_flags.dart` → `const bool kEnableFirebaseAuth = true;`
5. `flutter run` and verify Apple/Google sign-in completes against the real `nooto-dev` Firebase project (not the dev fake-auth bypass).

**Context:** Surfaced during `/plan-eng-review` PR2a (2026-04-30). Code path is already wired in `main.dart` and gated by the flag. The v2 auth service (`lib/services/auth_service.dart`) and provider (`lib/providers/auth_provider.dart`) were built earlier with the gate in mind.

**Depends on:** PR2a merged. Required before PR2b/PR2c can hit the v1 backend.

## Bound `home.actions.v1` retention to 90 days

**What:** On `main()` boot, compact the `home.actions.v1` Hive box by deleting rows whose `ts` is older than 90 days.

**Why:** The action log accumulates a row per dismiss / snooze / tap-through / open / accept. Over months of dogfood, thousands of rows. Unbounded local growth has no functional value beyond ~30–60 days; older rows aren't read by any generator's dedup check.

**Pros:**
- Keeps Hive open-box latency bounded at cold start.
- Trivial implementation (~5 lines): iterate keys, delete where `now - ts > 90d`.
- Invisible to the user.

**Cons:**
- Tiny scope creep on whichever sprint picks it up.
- Loses ability to do retention analytics from prior 90+ days (but no current analysis depends on that).

**Context:** Surfaced during `/plan-eng-review` of the Companion Stream Home design (2026-04-30). The full design doc is at `~/.gstack/projects/togodynamicslab-omi/matheusoliviera-main-design-20260430-111632.md` — see "Performance notes" section.

**Depends on:** Sprint 0 having shipped (`home.actions.v1` Hive box must exist). After that, do anytime.

## Extract `DESIGN.md` from `app_theme.dart` + Apple HIG conventions

**What:** Create `app-v2/DESIGN.md` consolidating the design system — colors (`AppColors`), spacing (`AppStyles`), typography (`brandSerif()`, Material text theme), touch targets, Apple HIG compliance rules, and the v2-specific Home grammar (voice vs surface cards, motion language).

**Why:** A real design system already exists but is spread across `lib/theme/app_theme.dart` + parent `omi/CLAUDE.md`. Future `/plan-design-review` runs will calibrate against it, future engineers won't re-derive conventions, and it answers "what does a card in v2 look like?" in one file.

**Pros:**
- Single source of truth for visual decisions.
- Future design reviews start higher (Pass 5 score lifts from 5/10 to 8+/10 by default).
- Onboarding for new contributors becomes one read of one file.

**Cons:**
- Documentation work that may drift from code if not maintained.
- One more file to keep in sync when theme tokens change.

**Context:** Surfaced during `/plan-design-review` of the Companion Stream Home (2026-04-30). The visual specification section of the design doc (`~/.gstack/projects/togodynamicslab-omi/matheusoliviera-main-design-20260430-111632.md`) is the seed — it already specifies card grammar, spacing rhythm, motion, accessibility for Home. Extracting and generalizing it produces DESIGN.md.

**Depends on:** Nothing structural. Best done after PR1 ships so the design system reflects shipped reality.
