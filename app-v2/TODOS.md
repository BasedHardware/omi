# TODOS — app-v2

Deferred work captured during planning. Add to a sprint when picking up.

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
