# Design System for Nooto — Desktop (Tauri + React)

> Scope: this file applies to **desktop-v2** (the Tauri/React/shadcn app). The Flutter (`app/`) and web (`web/landing/`) surfaces have their own DESIGN.md with the same brand DNA but platform-appropriate code examples.

## 1. Visual Theme & Atmosphere

Nooto is an AI companion that listens, remembers, and helps you act. The desktop app behaves the way the product behaves: **it listens more than it speaks**. The chrome stays out of the way, surfaces are layered with quiet opacity rather than hard contrast, and motion is small, snappy, and purposeful — never decorative. The product's job is to make you forget the app and remember your day.

The signature posture is **shadcn/ui new-york style with three Nooto-specific moves layered on top**:

1. **Single brand blue.** One color (`#3B82F6`) anchors every interactive surface — buttons, links, focus rings, the spinner orb. There is no secondary accent. When the app needs heat, it uses semantic destructive red; when it needs success, it uses muted green sparingly. Everything else is grayscale.
2. **Layered translucent surfaces, not raw contrast.** The visual hierarchy is built from **`bg-card` → `bg-secondary/40` → `bg-accent/50` (hover)** — a maximum of two opacity layers stacked. We never reach for shadow when an opacity tier will do.
3. **Snappy small-scale motion.** The sidebar collapses in 220ms. Active-nav indicators spring in at stiffness 500 / damping 35. There are no long fades, no elaborate page transitions, no parallax. Motion confirms an action and gets out of the way.

The voice is **warm, conversational, and lowercase-leaning**. Empty states say "No memories yet — your AI-extracted memories will appear here." not "NO MEMORIES FOUND." The recording toggle says "Start a meeting" not "Begin Audio Recording Session." First person ("I'll transcribe…") shows up in onboarding and HUDs, never in chrome.

**Key characteristics**

- **Brand blue `#3B82F6` everywhere primary**, no secondary accent color
- **shadcn/ui new-york** with CSS-variable theme, light + dark + system-aware
- **Layered opacity surfaces** (`/40`, `/50`) instead of stacked shadows
- **Snappy small-motion** (~220ms easeOut, stiff spring feedback)
- **Lucide icons only — no emoji in UI**
- **Inter for everything**; Playfair Display italic for brand emphasis ("Welcome to *Nooto*")
- **Sidebar-first navigation** with 4 primary destinations + 2 secondary, separated by hairline divider
- **Section tabs** (`SectionTabBar`) for route-based sub-pages; `PageHeaderFilter` pills for in-page state filters
- **Floating Tauri overlays** (Whispr HUD, Companion buddy, Floating bar) are always dark and decorationless, regardless of main-window theme

## 2. Color Palette & Roles

All colors are exposed as CSS variables in `src/styles/globals.css` and mapped to Tailwind utility classes via the inline `@theme` block. **Never write raw hex in component code** — reach for the semantic class.

### Brand
- **Nooto Blue** — `#3B82F6` (`oklch(0.585 0.19 265)`).
  Tailwind: `bg-primary`, `text-primary`, `border-primary`, `ring-primary`.
  CSS var: `--primary`, `--ring`, `--color-brand`.
  **Never override.** This is the same blue used in the Flutter app's `brand_colors.dart`. The Tauri ring color stays blue across both light and dark themes — the only chromatic constant that crosses theme boundaries.
- **Nooto Blue Light** — `#60a5fa` (`--color-brand-light`). Hover variants only.
- **Nooto Blue Dark** — `#2563eb` (`--color-brand-dark`, `--app-accent-hover`). Pressed / active state.

### Surface (light theme)
- **`--background` / `bg-background`** — `oklch(0.99 0 0)` (#fbfbfc). The main canvas.
- **`--card` / `bg-card`** — `oklch(1 0 0)` (#ffffff). Opaque cards floating on the canvas.
- **`--secondary` / `bg-secondary`** — `oklch(0.955 0 0)` (#f4f5f7). Sidebar, recessed panels. Often used at 40% (`bg-secondary/40`) to let canvas show through.
- **`--muted` / `bg-muted`** — `oklch(0.96 0 0)`. Disabled and de-emphasized fills.
- **`--accent` / `bg-accent`** — `oklch(0.93 0 0)`. Hover backgrounds, often at 50% (`bg-accent/50`).
- **`--border` / `border-border`** — `oklch(0.9 0 0)`. The default divider. Frequently dropped to `border-border/40` for hairlines.

### Surface (dark theme)
- **`bg-background`** — `oklch(0.145 0 0)` (#0a0a0a)
- **`bg-card`** — `oklch(0.145 0 0)` (cards match canvas in dark; layering comes from secondary/accent)
- **`bg-secondary`** — `oklch(0.269 0 0)` (#1a1a1a)
- **`bg-muted`** — `oklch(0.22 0 0)`
- **`bg-accent`** — `oklch(0.269 0 0)`

### Text
- **`text-foreground`** — primary text (~#18181b light / ~#ffffff dark).
- **`text-muted-foreground`** — secondary / metadata text. **By a wide margin the most-used text class** in the app (~250 occurrences). Reach for this before reaching for `text-foreground`.
- **`text-primary`** — links and inline brand emphasis only.
- **`text-destructive`** — errors and destructive confirmations.

### State
- **`text-destructive` / `bg-destructive`** — `oklch(0.58 0.22 27)`. Sign-out, delete, irreversible actions.
- **No green success token**. Successful state is the *absence* of error chrome, not a green pill. When a green is genuinely needed (capture armed indicator) reach for `text-green-500` directly with restraint.
- **Recording / live indicator**: `bg-red-500` with `animate-ping` halo — reserved for "currently capturing" feedback in the sidebar and HUDs.

### When to use which surface
- A page's full canvas → `bg-background`.
- A floating card on the canvas → `bg-card` + `border` + `rounded-xl` + `shadow-sm`.
- A section that recedes (sidebar, footer area, settings rail) → `bg-secondary/40`.
- A hover state on any interactive row → `bg-accent/50`.
- A hairline between sections → `border-border/40` (not `border-border` — too heavy).

## 3. Typography Rules

The app loads three families. Pick one based on the role; never mix more than two in a single screen.

### Families
- **Inter** — display, body, UI chrome, labels. **The default for everything.**
  Stack: `"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`.
  Tailwind: `font-display` (defined in `globals.css` `@theme`).
- **Playfair Display** — serif italic accents on brand emphasis only (e.g., "Welcome to *Nooto*", "Your AI *companion*"). Never for body, never upright.
  Tailwind: `font-serif italic`.
- **Lora** — alternative serif body for editorial passages (release notes, story briefings). Loaded from Google Fonts at weight 400–700 with full italic range. Use sparingly.
  Tailwind: `font-lora`.
- **SF Mono / Fira Code / Cascadia** — code blocks, transcripts, debug-panel readouts.
  CSS class: `.settings-value-mono` or `font-mono`.

### Sizes (Tailwind utilities — actual usage in the codebase)
- **`text-lg`** (18px) — page titles inside `PageHeader`. Headings in cards.
- **`text-base`** (16px) — primary body / chat text. Empty-state titles.
- **`text-sm`** (14px) — buttons, form inputs, list rows. **Minimum size for any interactive label.**
- **`text-xs`** (12px) — subtitles, metadata, filter pills, tooltips.
- **`text-[10px]`** — count badges only. Never for actionable text.
- **`text-[13px]`** — sidebar nav labels (a deliberate one-off between `text-xs` and `text-sm` to fit `h-8` rows comfortably).

### Weights
- **400** — body, default. Do not declare unless overriding.
- **500 (`font-medium`)** — buttons, nav labels, list-row primary text. The default for anything interactive.
- **600 (`font-semibold`)** — page titles, card headings.
- **700 (`font-bold`)** — reserved. Almost never appears in chrome; saved for emphasis inside dense markdown content.

### Brand emphasis pattern
The signature typographic move is **`font-display font-semibold` for the line + `font-serif italic` for the brand word**:

```tsx
<h1 className="font-display font-semibold text-lg">
  Welcome to <span className="font-serif italic">Nooto</span>
</h1>
```

Use in onboarding, empty states, and header welcomes. Do not use Playfair italic for anything other than brand-anchored words.

### Letter spacing & line height
- Default Tailwind `leading-*` values are correct for almost all cases.
- The sidebar header uses `tracking-wide` (`Sidebar.tsx:112`) — the only `tracking-*` override in the app. Don't add more.

## 4. Component Stylings

The component library is shadcn/ui (new-york style) with CSS variables, plus a small set of Nooto-custom primitives. Every component below has a canonical import path — use that, don't roll your own.

### Buttons (`src/components/ui/button.tsx`)
Six variants, seven sizes. Distribution in the codebase, in descending order of use:

- **`variant="ghost"`** — most-used. Dismiss buttons, secondary actions, icon-only chrome.
- **`variant="secondary"`** — settings panels, debug tools, filter chips.
- **`variant="outline"`** — cancel, "back to list" actions.
- **`variant="default"`** — primary CTAs (no `variant` prop). `bg-primary` blue.
- **`variant="destructive"`** — sign out, delete confirmations.
- **`variant="link"`** — inline text links inside body content.

Sizes: `default` (h-9), `sm` (h-8), `xs` (h-6), `lg` (h-10), and icon variants `icon-xs`/`icon-sm`/`icon`/`icon-lg`. Buttons inside list rows are `sm`; buttons in headers are `default`; floating action chips are `xs`.

### Cards (`src/components/ui/card.tsx`)
The standard surface: `bg-card border rounded-xl shadow-sm` with `p-6` interior. Use `<Card>` + `<CardHeader>` + `<CardContent>` + `<CardFooter>` rather than re-rolling the structure. `<CardAction>` exists as an auto-positioned slot for top-right actions.

### Inputs (`src/components/ui/input.tsx`, `textarea.tsx`, `select.tsx`)
Inputs are **`h-9` with a transparent background**, `border-input` border, and a 3px focus ring at 50% opacity:

```
focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50
```

Textareas use `min-h-16` with `field-sizing-content` so they grow with content. For any input that needs a prefix or trailing button, use `<InputGroup>` (`src/components/ui/input-group.tsx`) — don't compose flex wrappers manually.

### Page header (`src/components/ui/page-header.tsx`)
Every primary page begins with `<PageHeader title="…" subtitle="…" actions={…}>`. Layout: `border-b border-border/40 px-6 py-4`. Title is `text-lg font-semibold`; subtitle is `text-xs text-muted-foreground`.

For in-page filters (e.g., "Themes / People & Things" inside Memories), drop `<PageHeaderFilters>` as children and use `<PageHeaderFilter>` chips. Active state: `bg-foreground text-background`. These are **state filters**, not route changes.

### Section tab bar (`src/components/library/SectionTabBar.tsx`)
Used by Library and Plan to switch between **sub-routes** (`/library/meetings` ↔ `/library/memories`). Visually subtler than `PageHeader`: a thin `bg-secondary/30` strip with `rounded-full` pill `NavLink`s. Active pill is `bg-foreground text-background`. **Use this when the tabs change the URL; use `PageHeaderFilter` when they only change local state.**

### Empty states
Pattern (from `ConversationEmptyState` in `src/components/ai-elements/conversation.tsx`):

```tsx
<div className="flex size-full flex-col items-center justify-center gap-4 p-8 text-center">
  <Icon className="size-8 text-muted-foreground/60" />
  <div className="space-y-1.5">
    <h3 className="font-medium text-base text-foreground">Title</h3>
    <p className="text-muted-foreground text-sm">Description.</p>
  </div>
  <Button variant="ghost" size="sm">Optional action</Button>
</div>
```

The icon is intentionally faded (`/60`) so the title leads. The optional action is `ghost`, never primary — empty states invite, they don't demand.

### Generative content
AI-generated message bodies render through `<GenerativeMarkdown>` (`src/components/generative-ui/`). The component understands a small XML tag vocabulary:

- `<markdown>` — prose, code, math, mermaid (default)
- `<richList>` — title + description + thumbnail + url
- `<chart type="bar|pie|donut">` — labeled segments
- `<accordion>` — collapsible groups
- `<highlight color="…">` — inline highlighted text
- `<table>` — structured rows
- `<storyBriefing>` — timeline + quoteboard + followups for daily summaries

**Use these when an AI response has structured shape.** Don't render structured content as raw markdown — the XML tags get a much better-styled rendering.

### Icons
Lucide React, always. Import inline:

```tsx
import { Home, MessageSquare, Library } from "lucide-react";
```

Default size is `size-4` (16px) inside buttons; `size-3.5` (14px) inside compact filter chips and tab pills; `size-5` for primary nav header icons. **Emoji are forbidden in chrome.** They appear only inside data files (`src/components/goals/emoji.ts`) as a category mapping that gets translated to Lucide icons in the UI.

### Spinners & loading
Spinner component is `<Spinner />` from `src/components/ui/spinner.tsx` — wraps `Loader2Icon` with `animate-spin` + ARIA labels. For inline progress text use lowercase ellipsis: "Loading insights…", "Writing summary and action items…".

There is no skeleton component. Use a spinner or text placeholder; do not introduce skeleton bars.

## 5. Layout Principles

### App shell (`src/App.tsx`)
```tsx
<div className="app-container">    // height: 100vh, width: 100vw, flex
  <Sidebar />                       // 220px expanded / 52px collapsed
  <main className="main-content">   // contain: layout paint
    <KeepAliveRoutes />             // lazy-mount, hide via display:none
  </main>
  <MemoryIndicator />               // overlay: bottom-right toast
  <GoalCelebrationOverlay />        // overlay: full-screen burst
</div>
```

Routes are **lazy-mounted on first activation, then kept alive via `display: none`** — never unmounted. This is the convention for the desktop app: state survives navigation, scroll positions persist, hot tab switches are instant. When you add a new top-level page, register it in `KeepAliveRoutes`, not in a fresh `<Routes>` block.

### Sidebar (`src/components/sidebar/Sidebar.tsx`)
- **Width**: `EXPANDED = 220`, `COLLAPSED = 52`, `ICON_PL = 10` (icon left padding).
- **Collapse**: `⌘B` / `Ctrl+B`, plus an edge-divider button.
- **Animation**: single motion value drives width + label opacity. Width interpolates 52→220; opacity uses a 3-stop transform `[0, 0.5, 1] → [0, 0, 1]` so labels never sub-pixel-render mid-animation. Easing `[0.32, 0.72, 0, 1]`, duration 0.22s.
- **Primary nav (4 items)**: Home, Chat, Library, Plan. Each is `h-8 rounded-lg` with active state `bg-accent text-foreground`.
- **Secondary nav (2 items)**: Apps, Devices. Visually demoted by a `my-2 mx-1 h-px bg-border/40` divider. Same row styling, just farther down.
- **Footer**: `AuraToggle` (Rewind+Focus capture switch) and `AudioToggle` (start-meeting w/ language popover), then a `ProfileMenu` with avatar + email and a Settings dropdown.
- **Active indicator** when collapsed: a 3px-wide `bg-foreground` left bar with `layoutId="active-indicator"` so it slides between items via spring (`stiffness: 500, damping: 35`).

### Library and Plan (tabbed sub-sections)
The 4 primary destinations include two "rollup" surfaces:

- **`/library/*`** — Meetings · Memories · Rewind · Whispr. (Captured outputs.)
- **`/plan/*`** — Tasks · Goals · Insights. (Derived actions.)

Each rollup is implemented as a `LibraryPage` / `PlanPage` shell that renders a `SectionTabBar` and the matching child page. Pre-rollup paths (`/meetings`, `/tasks`, `/focus`, etc.) are preserved as `<Navigate replace>` redirects in `App.tsx` so old deep links and in-app `navigate()` calls keep working.

When a feature has 3+ related views that share an audience, group it into a tabbed rollup. When a feature is standalone, give it a top-level slot. **Don't add destinations to the primary sidebar; consolidate into Library or Plan.**

### Page composition
Every primary page is `<PageHeader> + scrollable content`:

```tsx
<div className="flex h-full flex-col">
  <PageHeader title="Meetings" subtitle="12 conversations · 3 today" actions={…}>
    <PageHeaderFilters>…</PageHeaderFilters>
  </PageHeader>
  <div className="flex-1 overflow-hidden">
    {/* page body */}
  </div>
</div>
```

### Density (row heights)
- **Sidebar nav row** — `h-8` (32px)
- **Sidebar footer toggle** — `h-9` (36px)
- **Profile menu trigger** — `h-10` (40px)
- **Sidebar header** — `h-12` (48px)
- **Buttons (default)** — `h-9` / `h-8` / `h-10`
- **Inputs** — `h-9`
- **PageHeader** — `py-4` (~52px tall with subtitle)
- **SectionTabBar** — `py-1.5` (~32px)
- **Conversation cards** — `py-2.5` with auto-grow

Pick from this scale. **Don't introduce new heights.** If a one-pixel adjustment is tempting, the answer is almost always to use the next stop on the scale.

### Spacing
Tailwind's default scale is the system. Most-used in code:

- `gap-2` (8px) — within rows of icons + label
- `gap-1` (4px) — chip clusters, tight inline
- `gap-3` (12px) — group spacing
- `px-6 py-4` — page-header padding
- `p-8` — empty-state container

The radius base is `--radius: 0.75rem` (12px), with derived `-sm` (8px), `-md` (10px), `-lg` (12px), `-xl` (16px). Pills use `rounded-full`. Cards default to `rounded-xl`. Buttons default to `rounded-md`.

### Floating Tauri overlays
Five separate windows defined in `src-tauri/tauri.conf.json`:

- **Floating bar** (500×120) — quick "Ask Nooto" input
- **Whispr HUD** (120×80) — live transcription orb
- **Live transcript** (420×240) — full conversation viewer
- **Companion buddy** (96×96) — draggable persona orb
- **Main window** — the app shell above

All overlays are `transparent: true`, `decorations: false`, **forced dark theme** regardless of user preference (the FOUC script in `index.html` and `main.tsx` short-circuits the theme store for these windows). When designing a new overlay, follow this convention — overlays are instruments, not pages.

## 6. Depth & Elevation

| Level | Treatment | Use |
|---|---|---|
| 0 | No shadow | Default content on `bg-background` |
| 1 | `shadow-xs` | Buttons (outline variant), input groups |
| 2 | `shadow-sm` | Cards, popovers |
| 3 | `shadow-md` | Dialogs, dropdowns |
| 4 | `shadow-lg` | Toast/alert overlays (rare) |
| 5 | Focus ring `ring-3 ring-ring/50` | Every focused interactive element |
| 6 | `ring-1 ring-border` | Subtle container outline (settings cards) |
| 7 | `backdrop-blur` + `bg-secondary/30` | Sticky filter bars, HUD chrome |

Elevation is **whispered, never shouted**. Most of the app sits flat. Cards float at `shadow-sm`; modals at `shadow-md`. The app does not use `shadow-xl` or `shadow-2xl` — if you reach for one, layer surface opacity instead (`bg-card` over `bg-secondary/40`).

**Focus is signaled by a 3px ring at 50% opacity, not by a shadow change.** This is consistent with shadcn defaults and matches the Flutter app's focus treatment.

## 7. Do's and Don'ts

### Do
- **Do** use semantic Tailwind classes (`bg-primary`, `text-muted-foreground`, `border-border`) — never raw hex. The theme tokens carry both light and dark mode automatically.
- **Do** use `text-muted-foreground` as the default for secondary text. It is the most-used text class in the app for a reason.
- **Do** use `bg-secondary/40` for sidebars and recessed panels, `bg-accent/50` for hover states. Two opacity layers maximum.
- **Do** use `<PageHeader>` at the top of every primary page. Match its `px-6 py-4` rhythm.
- **Do** use `<SectionTabBar>` when sub-tabs change the URL; use `<PageHeaderFilter>` when they change local state.
- **Do** stick to `text-sm` minimum for any interactive label. `text-xs` is for metadata only.
- **Do** use Lucide icons at `size-4` inside buttons and `size-3.5` inside chips/tabs.
- **Do** apply `font-serif italic` to the word "Nooto" when it appears in display contexts. That italic Playfair is the brand emphasis.
- **Do** keep motion under 300ms. Snappy easeOut for layout, stiff springs for feedback indicators.
- **Do** preserve old routes as redirects when restructuring (`App.tsx`'s `LEGACY_REDIRECTS` is the pattern).
- **Do** force dark theme in any new Tauri overlay window.

### Don't
- **Don't** introduce a secondary brand color. Nooto blue (`#3B82F6`) is the only chromatic anchor; success and recording use red/green only as state indicators.
- **Don't** use emoji in chrome. Lucide icons everywhere. Emoji exists only in data mappings, never in JSX.
- **Don't** use `text-xs` for buttons or any interactive label. 14px floor.
- **Don't** stack shadows for hierarchy — layer surface opacity instead. `shadow-xl` and `shadow-2xl` do not appear in the app.
- **Don't** introduce new row heights or radius values. Pick from the existing scale.
- **Don't** add destinations to the primary sidebar without first asking whether they belong inside Library or Plan.
- **Don't** unmount kept-alive routes. Add new top-level pages to `KeepAliveRoutes`, never to a fresh `<Routes>` block.
- **Don't** use long fades, parallax, or page-transition animations. Motion is small and confirmatory only.
- **Don't** use ALL-CAPS labels. Sentence case for everything; metadata may be lowercase.
- **Don't** build a custom Skeleton; use the spinner or a lowercase progress sentence.
- **Don't** mix more than two type families on a screen.

## 8. Responsive Behavior

The desktop app is **fixed-layout, desktop-only**. Tailwind breakpoints exist but are barely used (≤10 occurrences). Layout responds to **window width via the sidebar collapse**, not via media queries.

### Window sizing
- **Main window**: minimum 800×600, default 1200×800, resizable. Native title bar (Tauri `decorations: true`).
- **Sidebar collapse**: triggered by user (⌘B) or programmatically when window width drops below comfortable viewing. The collapsed 52px sidebar still shows icons + tooltips on hover, so all primary nav is reachable at any size.
- **Floating overlays**: fixed sizes, always-on-top, never resize with main window.

### When media queries are appropriate
- Login screen (`sm:max-w-*`) — keeps form readable on a tiny window.
- Settings panels — occasional `md:` for two-column layouts on wide screens.
- Almost nothing else. If you find yourself reaching for `lg:` / `xl:`, ask whether the design should adapt or whether the window should just be wider.

### Touch targets
This is a desktop app — **mouse-first**. Apple HIG's 44pt rule does not apply. Standard interactive heights are `h-8` (32px), `h-9` (36px), and `h-10` (40px). The companion buddy orb (96×96) is the only intentionally large touch target and it's optimized for *drag*, not tap.

## 9. Agent Prompt Guide

### Quick token reference
- **Primary brand fill** — `bg-primary` (Nooto Blue `#3B82F6`)
- **Primary brand text** — `text-primary`
- **Focus ring** — `focus-visible:ring-[3px] focus-visible:ring-ring/50`
- **Page canvas** — `bg-background`
- **Floating card** — `bg-card border rounded-xl shadow-sm p-6`
- **Recessed panel (sidebar, footer)** — `bg-secondary/40`
- **Hover row** — `bg-accent/50`
- **Hairline divider** — `border-border/40`
- **Default body text** — `text-foreground`
- **Secondary / metadata text** — `text-muted-foreground`
- **Brand italic accent** — `<span className="font-serif italic">Nooto</span>`
- **Destructive** — `bg-destructive` / `text-destructive`
- **Recording / live** — `bg-red-500` + `animate-ping` halo

### Component decision tree
- **Need a button?** → `<Button>` from `@/components/ui/button` with the right variant.
- **Need a card?** → `<Card>` from `@/components/ui/card`.
- **Need an input with prefix/suffix?** → `<InputGroup>` from `@/components/ui/input-group`.
- **Need a page-level header?** → `<PageHeader>` from `@/components/ui/page-header`.
- **Need filters that change local state?** → `<PageHeaderFilter>` inside `<PageHeaderFilters>`.
- **Need tabs that change the URL?** → `<SectionTabBar>` from `@/components/library/SectionTabBar`.
- **Need to render AI-generated structured content?** → `<GenerativeMarkdown>` from `@/components/generative-ui/GenerativeMarkdown`.
- **Need a tooltip?** → `<Tooltip>` from `@/components/ui/tooltip` — always inside `<TooltipProvider>` (already provided by `App.tsx`).
- **Need a dialog?** → `<Dialog>` from `@/components/ui/dialog`. Don't roll a custom modal.
- **Need a hover-only row affordance?** → use `bg-accent/50` on hover, no shadow change.

### Example component prompts
1. *"Build a Conversations list row at `h-9` with a 16px Lucide icon at `size-4 text-muted-foreground`, a primary label in `text-sm font-medium text-foreground`, a metadata line in `text-xs text-muted-foreground`, and a hover state of `bg-accent/50`. The whole row is `rounded-lg`. No shadow."*
2. *"Build an empty state for the Insights tab using the `ConversationEmptyState` pattern: a `Lightbulb` icon at `size-8 text-muted-foreground/60`, an `text-base font-medium` title 'No insights yet', a `text-sm text-muted-foreground` description, and a single `Button variant=\"ghost\" size=\"sm\"` action 'Connect a calendar'."*
3. *"Build a setting card on a `bg-card border rounded-xl shadow-sm p-6` surface. Heading is `text-base font-semibold`, helper is `text-sm text-muted-foreground`. The control row uses `<Switch>` from `@/components/ui/switch` aligned right. Use `gap-3` between heading and helper."*
4. *"Add a new top-level destination 'Inbox' to the primary sidebar. Register the route in `App.tsx`'s `KeepAliveRoutes` (do not introduce a new `<Routes>` block). Add the entry to `primaryNav` in `Sidebar.tsx` with a Lucide `Inbox` icon. If the new feature has multiple sub-views, build it inside Library or Plan instead."*
5. *"Build a Tauri overlay window for a 'Quick capture' surface: 360×120, `transparent: true`, `decorations: false`, always-on-top. Force dark theme via the FOUC script (already in `index.html`). The body uses `bg-secondary/30` with `backdrop-blur` and `rounded-2xl border border-border/30`."*

### Iteration audit
When refining an existing screen for consistency:

1. **Audit colors.** Every fill and text class should be a shadcn semantic var. If you see `#hex`, `bg-gray-*`, or `text-zinc-*`, replace with `bg-secondary/*`, `text-muted-foreground`, etc.
2. **Audit text sizes.** No interactive label below `text-sm`. No `text-xs` on buttons.
3. **Audit row heights.** Pick from `h-8` / `h-9` / `h-10` / `h-12`. No `h-7`, no `h-11`.
4. **Audit shadows.** If you see `shadow-xl` / `shadow-2xl` / multi-stop custom box-shadows, replace with surface opacity layering.
5. **Audit icons.** Every icon should be a Lucide import. If you see emoji or PNG icons in chrome, replace with Lucide.
6. **Audit motion.** Anything over 300ms is too slow for chrome. Anything springy outside `stiffness: 400–500` likely overshoots.
7. **Audit nav structure.** New destinations should be inside Library or Plan, not new top-level sidebar items. Confirm the URL is registered in `KeepAliveRoutes`.
8. **Audit voice.** Sentence case, lowercase progress ellipsis, no exclamation marks except in error states. The product listens more than it speaks; chrome copy follows the same rule.
