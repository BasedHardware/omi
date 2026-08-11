# web/app — destinations, chrome, and the runtime's motion traps

Companion to [`web/app/AGENTS.md`](../../web/app/AGENTS.md). Read before adding a
page, moving a surface between pages, or debugging an animation that looks stuck.

## One rail entry per destination, one place per idea

| Route | Holds |
|---|---|
| `/home` | The hub **and** the chat. Chat is not a separate page: `web/app/src/components/home/HomePage.tsx` keeps recent history above the hub and the current exchange below it, with transcript rendering owned by `web/app/src/components/chat/ChatTranscript.tsx`. Live capture also starts here, from the composer. |
| `/conversations` | Conversations and daily recaps in one day-grouped gallery. A recap is the summary of a day, so it leads that day rather than living in a list of its own. |
| `/memories`, `/tasks` | As named. |
| `/connectors` | Installed apps **and** external services — the former Settings → Integrations. |
| `/settings` | Account (profile and plan merged), Privacy, Developer. |

Removed rather than redirected, so do not re-add aliases for them:
`/chat`, `/recaps`, `/my-apps`, `/persona`.

The macOS app is the reference for this shape: chat has no rail row there
either, and Home shows no stat counters. See `desktop/macos/Desktop/Sources/MainWindow/`.

## Page chrome

`web/app/src/components/layout/PageToolbar.tsx` is the one top row: a left slot for view
controls, a right-aligned search field, a right slot for actions. It renders
**no page title** — the sidebar is the only thing that names the page, and a
heading repeating it is a second answer to a question nobody asked. Pages match
because they share this component, not because someone kept them in sync.

`PageHeader` is the different thing it looks like: a back button beside a title,
for detail and sub pages.

shadcn/ui is set up (`web/app/components.json`, primitives in `web/app/src/components/ui/`
lowercase). Its generator emits literal `oklch(...)` strings, which are not
valid classes in this project, so every primitive is restyled onto the Omi
tokens on the way in. Do that for any primitive you add.

The accent is white and no purple tokens remain to reach for
([INV-UI-1](../product/invariants/brand-ui.md)).

## Runtime floor

Needs `@tschk/moonshine` **>= 0.3.7**. Before it, the router's location signal
carried only the pathname, so a navigation changing only the query wrote the
same value back and notified nobody: every `useSearchParams` caller in an
already-mounted tree kept rendering the previous query. A settings tab bar
driven by `?section=` changed the URL and not the page.

## Two motion traps, both already paid for

**The shell remounts on every navigation.** Each route registers its own copy of
the authenticated layout, so navigating is a fresh mount rather than a re-render.
`AnimatePresence initial={false}` exists precisely to suppress the enter
animation on a first render, so using it here suppresses the transition on
*every* navigation. Use a plain keyed `initial`, which animates on both a
remount and an in-place key change. For the same reason there is no exit
animation to be had: the outgoing tree is gone before the new one mounts.

**A hidden tab freezes rAF and CSS transitions.** An animation inspected through
a backgrounded browser reads as permanently stuck at its initial frame —
`height: 0`, `opacity: 0`, whatever `initial` set. Check
`document.visibilityState` before concluding an animation is broken, or set
`transition: none` and read the resting value. This cost real time on this
branch: a working menu was rewritten three times before the tab was the answer.

## Layout gotcha worth knowing

The rail is a flex column whose nav takes the slack, so anything in the footer
that must not be squeezed needs `flex-shrink-0`. Without it an expanding panel
is silently compressed back to its collapsed height, which looks exactly like an
animation that failed to run.
