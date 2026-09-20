# Owned Base UI / shadcn preview

This is a development-only DOM experiment, not a replacement for the React
Native product. Run `bun run --cwd pwa dev` from the repository root and open
`/base-ui-preview.html?data=example`. Add `&surface=mobile` for the narrow,
dark surface. Without example data it opens an empty state; `data=loading`
and `data=error` exercise unsettled reads.

`components.tsx` contains locally owned shadcn Base Nova adaptations backed
by `@base-ui/react`. `preview.css` owns the neutral light/dark theme; its
Tailwind source scan and styles are confined to this entry. See `NOTICE.md`
for MIT attribution. No Hana code or runtime token mutation remains.

The daily brief uses the same `homeBriefing` function as native Desktop Home.
Completing a fixture task updates the priority. Search filters the local tasks
and conversation titles/summaries. Tabs support keyboard navigation. Settings
can change the preview theme. Ask, Recall and connections explicitly report
their preview limitations; there are no account requests, capture, telemetry,
or persisted edits. Glass remains a browser approximation.

The production entry and native components stay React Native. Vite's normal
build excludes this HTML entry. Check with `bun run --cwd pwa typecheck`,
`bun run --cwd pwa test`, and `bun run --cwd pwa build`; shared daily-brief
behavior is covered by `DesktopApp.test.tsx`. Run `bun run check` before
publishing and disclose baseline failures separately.
