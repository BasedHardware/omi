# Design System — Nooto v2

> Anchor: **Apple Human Interface Guidelines** (iOS), adapted where the product
> thesis demands. Existing tokens live in `lib/theme/app_theme.dart`; this file
> is the source of truth for *why* they are what they are.

## Product Context

- **What this is:** Nooto v2 — a proactive AI companion mobile app, pendant-first, with a Companion Stream Home (assistant-generated cards, not a transcripts dashboard).
- **Who it's for:** Pre-launch, founder-as-user (Matheus). Validation loop is dogfood, not external research.
- **Space:** AI personal assistant / "chief of staff" category. Direct peers: Omi (upstream fork), Limitless. Adjacent: Notion AI, Granola, Reflect.
- **Project type:** Flutter mobile app, iOS-primary (Android works but iOS is the polish target).
- **Posture:** Looks and feels like a serious native iOS app. Not a Flutter cross-platform compromise. HIG fluency is non-negotiable; departures are intentional and documented.

## Aesthetic Direction

- **Direction:** **Brutally minimal with one expressive accent.** Typography and whitespace do the work. Brand blue + serif italic is the only "voice" the system raises.
- **Decoration level:** **Minimal.** No gradients, no decorative blobs, no shadows beyond what HIG uses for elevation. Borders at `Colors.white.withValues(alpha: 0.06)` are the most chrome we add.
- **Mood:** Calm, intelligent, deliberate. The product should feel like it knows you, not like it's selling itself to you.
- **Memorable thing:** A serious iOS app that happens to be an AI companion — not an AI app that happens to run on iOS. The HIG fluency IS the trust signal.

## Apple HIG Alignment (where we comply)

| HIG principle | Where we honor it |
|---|---|
| Minimum 44pt touch target | `AppStyles.touchTargetMinimum = 44.0`; `HeaderIconButton`, `_ActionButton`, `_SeeAllRow` all enforce |
| Standard nav bar height (44pt) | `ShellScreen` AppBar uses Material default |
| Tab bar 49pt + safe area | `ShellTabBar` computes `MediaQuery.padding.bottom` dynamically |
| Body text ≥ 16pt, button labels ≥ 14pt | Theme `bodyLarge: 16`, `labelLarge: 14`; never go below in interactive elements |
| Native dark mode (true blacks + elevation tower) | 4-step neutral tower `#0F0F0F → #2A2A2A`; surfaces lift, not invert |
| Off-white for body text in dark (~`#E0`) | `textSecondary: #E5E5E5` |
| Native motion (ease-out enter, ease-in exit, 150-300ms) | `CardEntrance` uses 180ms `Curves.easeOut` |
| `prefers-reduced-motion` | Honored by Flutter's animation system; reduced-motion skips entrance |

## Intentional Departures from HIG

These are deliberate. Each serves the chief-of-staff thesis.

1. **Voice cards (welcome, morning brief) have NO chrome.** HIG would put them in a `UITableView` cell or grouped style. We render them as direct text on the screen background so they read as the assistant *speaking*, not as a tile in a dashboard. The contrast against the chromed Today surface card creates the speaking-vs-list grammar the product depends on.
2. **Chat-pattern Home (composer docked at bottom).** HIG primary nav lives at top or via tab bar. We keep both AND add a chat composer pill at the bottom because "Ask Nooto anything" is a co-equal entry point, not a setting buried in a screen. The pill is a `GestureDetector`, not a `TextField`, so taps navigate immediately without keyboard-flash.
3. **One accent color, no segmentation by type.** HIG often differentiates with multiple tints (system blue for actions, system red for destructive, system green for confirmation). We use brand blue for both primary actions AND emphasis (eyebrow text, See all, Got it). Destructive uses a textTertiary X icon instead of red. The restraint means when red DOES appear, it means real failure.

## Typography

System sans-serif only. iOS gets SF Pro automatically, Android gets Roboto. No custom font face anywhere in the product.

| Role | Size | Weight | Used for |
|---|---|---|---|
| Brand emphasis (large) | 30-34pt | 700 | Welcome tagline emphasis, Home large title wordmark |
| Brand emphasis (compact) | 17-22pt | 600-700 | Voice card greeting, compact bar wordmark, hero one-liners |
| Display | 36pt | 600 | Reserved for hero screens (none on Home today) |
| Headline | 22pt | 600 | Section headers (rare; we lean on labelLarge instead) |
| Body large | 16pt | 400 | Card body text (welcome paragraph, brief body) |
| Body medium | 14pt | 400 | Bullets in Today card, secondary chrome |
| Label large | 14pt | 500 | Buttons, eyebrows, "See all", tab labels |
| Caption | 12pt | 400-600 | "Action item" eyebrow, relative time, source line |

Brand emphasis comes from **weight + size + letter-spacing**, never from a different typeface. The `brandEmphasis()` helper in `app_theme.dart` is the single allowed channel for emphasis text — it returns a system-font TextStyle with -0.2 letter-spacing.

**Why no custom font:** Apple licensing prevents shipping SF Pro in non-iOS builds. Loading a custom sans like Inter would fight HIG on iOS *and* introduce a font-loading flash. Custom serif (e.g. Playfair) was tried and explicitly rejected — too literary for the chief-of-staff role and out of step with the rest of the product surface.

**Hard blacklist — never reintroduce:**
- Any serif face (Playfair, Times, Georgia, etc.). Serif emphasis is permanently off the table for this product.
- Italic as a brand-emphasis lever (italic was the wrapper we used for serif; without serif there's no reason to italicize for brand).
- Custom sans (Inter, Roboto, Poppins, Space Grotesk) as primary brand font.
- Cursive, handwritten, or decorative display faces.
- The previous `brandSerif()` helper. Use `brandEmphasis()` instead.

## Color

**Approach:** Restrained. One accent + neutral tower + semantic.

### Neutrals (dark mode only)

| Token | Hex | Role |
|---|---|---|
| `backgroundPrimary` | `#0F0F0F` | Scaffold / screen background |
| `backgroundSecondary` | `#1A1A1A` | Surface cards (Today, action item chrome) |
| `backgroundTertiary` | `#252525` | Hover/pressed states, modal sheets |
| `backgroundQuaternary` | `#2A2A2A` | Highest elevation (rare) |

The 4-step tower follows HIG's "elevation by lightness" principle for dark mode. Distance between adjacent steps is 5-7% lightness — enough to register as different surfaces under fluorescent lighting and pendant glances.

### Text

| Token | Hex | Role | Contrast on `#0F0F0F` |
|---|---|---|---|
| `textPrimary` | `#FFFFFF` | Headings, primary body | 21:1 |
| `textSecondary` | `#E5E5E5` | Default body (HIG-aligned off-white) | 18:1 |
| `textTertiary` | `#B0B0B0` | Captions, eyebrows, dismiss icons | 9.5:1 |
| `textQuaternary` | `#888888` | Disabled, placeholders | 5.7:1 |

All four pass WCAG AA on the entire neutral tower. `textQuaternary` is the floor — never use for interactive labels.

### Brand

| Token | Hex | Role |
|---|---|---|
| `brandPrimary` | `#3B82F6` | Primary CTA, action item eyebrow, See all link, brief streaming caret |
| `brandAccent` | `#2563EB` | Pressed state of brandPrimary |
| `brandLight` | `#93C5FD` | Reserved (not used today) |

**Why this blue:** matches the landing site and `desktop-v2`. It's close enough to iOS system blue (`#007AFF`) that HIG-trained eyes don't reject it, but slightly cooler/desaturated to feel less stock. The brand consistency across mobile + desktop + web is a deliberate signal: same product, three surfaces, one company.

### Semantic

| Token | Hex | Role |
|---|---|---|
| `successColor` | `#10B981` | Confirmation states (rare today) |
| `warningColor` | `#F59E0B` | Caution / non-blocking warnings |
| `errorColor` | `#EF4444` | Real failures only — never used for routine destructive actions |

## Spacing

**Base unit:** 4pt. **Density:** comfortable (mid-density between iOS Mail and Notion).

| Token | Value | Usage |
|---|---|---|
| `spacingXS` | 4pt | Tight groupings (icon + label inside a row) |
| `spacingS` | 8pt | Adjacent UI elements that belong together |
| `spacingM` | 12pt | Between sub-elements within a card |
| `spacingL` | 16pt | Card padding, between top-level rows |
| `spacingXL` | 24pt | Between sections, AppBar to first card |
| `spacingXXL` | 32pt | Major section breaks |

The Home screen rhythm uses these as: `spacingXL` AppBar→first voice card, `spacingL` between voice and surface cards, `spacingL` between consecutive surface cards, `spacingXL` last card to composer, 8pt composer to safe-area inset.

## Layout

- **Approach:** Vertical stack with chat-pattern composer dock. Cards flow top-down by priority. No grid columns on mobile.
- **Card priority:** welcome (1000) > brief (750) > today (500). Higher = floats up.
- **Max content width:** N/A (single-column mobile). Tablet/iPad treatment is deferred.
- **Border radius:**

| Token | Value | Usage |
|---|---|---|
| `radiusSmall` | 6pt | Inline pills, small buttons (rare) |
| `radiusMedium` | 8pt | Action buttons, input fields |
| `radiusLarge` | 12pt | Surface cards (Today) |
| `radiusXLarge` | 20pt | Composer pill, hero containers |
| `radiusPill` | 999pt | Full-pill buttons (Apple chip style) |

**Inner radius rule (HIG):** when nesting, inner radius = outer radius − inner padding. We don't enforce in code today; flag during review.

## Motion

- **Approach:** **Minimal-functional with one signature.** Card entrance is the only deliberate motion; everything else is default Flutter spring/ease behavior.
- **Card entrance:** `FadeTransition` 180ms `Curves.easeOut` + `SlideTransition` 4% translate-y from below. Defined once in `lib/home/cards/card_entrance.dart`, reused by all cards.
- **Brief streaming (PR2c+ when streaming UI lands):** caret cursor `▎` blinks at 1Hz at end of partial text; fades over 200ms on stream complete.
- **No page transitions:** tab switches use `IndexedStack` (instant, no animation). HIG-compliant for tab bars.
- **Reduced motion:** Flutter's `MediaQuery.of(context).disableAnimations` is honored by `FadeTransition`/`SlideTransition` automatically.

## Card Grammar (the locked decision)

Two card kinds with different chrome:

**Voice cards** — `welcome_card`, `morning_brief_card`. No bordered container, no fill, no shadow. Direct text on `backgroundPrimary`. Padded with `spacingL` horizontal / `spacingM` vertical. Reads as the assistant *speaking*.

**Surface cards** — `today_card`, future `commitment_capture`, `focus_block`. `backgroundSecondary` fill, `radiusLarge`, `Border.all(Colors.white.withValues(alpha: 0.06))`, `EdgeInsets.all(spacingL)` padding. Reads as a structured affordance.

This is the most important visual decision in the system. Stacking multiple surface cards = dashboard mode (anti-pattern, hard rejection from `/plan-design-review`). The hierarchy on Home is: voice first, surface below, max one surface per content domain.

## Accessibility

- All tap targets meet 44pt minimum (enforced by `AppStyles.touchTargetMinimum`).
- `Semantics(label: ...)` wraps every card with a screen-reader label that aggregates the visible content.
- Color contrast: every text/background combo passes WCAG AA (verified in the Color section).
- Action item bullets in Today card are individually focusable so VoiceOver navigates row-by-row (deferred to Day-30 when we add per-bullet actions).
- No color-only encoding — eyebrow says "Action item" in text, dot color reinforces.
- Reduced motion respected via Flutter platform integration.

## Light Mode

**Out of scope.** App is dark-only, inherited from upstream Omi convention and the pendant-glance use case (low-light environments where dark UI doesn't blast retinas). Light mode would be a cross-tab decision, not a design-system fix.

## What's NOT in this system (anti-patterns)

The following are explicit rejections — flag during review if any appear:

- Purple/violet/indigo gradient backgrounds
- 3-column feature grid with icons in colored circles (the SaaS landing-page tell)
- Centered everything (`text-align: center` on all cards)
- Uniform bubbly border-radius applied to every element
- Colored left-border on cards (`border-left: 3px solid <accent>`)
- Decorative blobs, floating circles, wavy SVG dividers
- Emoji as design elements (rockets in headings, emoji bullets) — **forbidden in UI per project CLAUDE.md**
- Generic hero copy ("Welcome to Nooto", "Unlock the power of...", "All-in-one")
- Stacked cards mosaic (instant rejection — see Card Grammar)
- Cookie-cutter section rhythm (hero → 3 features → testimonials)
- **Serif typography of any kind** (Playfair, Times, Georgia) — permanent blacklist; brand emphasis comes from sans-serif weight + size only

## Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-04-30 | Initial DESIGN.md created | Formalize tokens already shipped in `app_theme.dart`; anchor to Apple HIG; codify the voice/surface card grammar locked in `/plan-design-review` |
| 2026-04-30 | Voice cards drop chrome | Hard rejection rule from `/plan-design-review` — stacking cards reads as dashboard |
| 2026-04-30 | One accent color (brand blue) | Restraint; lets red mean real failure |
| 2026-04-30 | Playfair Display Italic for brand serif | Editorial gravity without script informality; matches `desktop-v2` |
| 2026-04-30 | **Serif reversed — no serif anywhere, ever** | Founder dogfeed rejected Playfair on sight ("I hate serif fonts"). Brand emphasis switches to sans-serif weight + size only; `brandSerif()` deleted; google_fonts dropped from pubspec; permanent blacklist added to anti-patterns |
| 2026-04-30 | Light mode out of scope | Dark-only inherited from upstream + pendant-glance use case |
