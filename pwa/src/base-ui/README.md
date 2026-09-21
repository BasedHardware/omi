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
and conversation titles/summaries. Home's glance strip shows incomplete tasks
due on the local calendar day, completed/loaded task counts, and usable completed
conversation counts. Counts describe loaded data, not unseen pages; unsettled or
failed reads show a dash rather than zero. Each cell opens its corresponding list.
Tabs support keyboard navigation. Settings owns Apps and can change the preview
theme. Ask, desktop Recall and connections explicitly report
their preview limitations; there are no account requests, capture, telemetry,
or persisted edits. Glass remains a browser approximation.

Desktop chrome shows non-interactive traffic lights and an icon-only Settings
button beside the Recall capture toggle. The toggle switches a neutral monitor
to a green monitor-with-dot, but only simulates state; it never starts capture.
It does not add a status line. Ask, Search and Recall are labelled icon buttons
inside the desktop omnibar; mobile has only Ask and Search. Mobile has no header
or Recall surface and retains its Search default and labelled bottom navigation.
The Home tab reuses the native `OmiAvatar` ink mark, breathing only while Home is
active and becoming static when the live system Reduce Motion preference is on.
Home has no Screen history card on either surface.

The production entry and native components stay React Native. Vite's normal
build excludes this HTML entry. Check with `bun run --cwd pwa typecheck`,
`bun run --cwd pwa test`, and `bun run --cwd pwa build`; shared daily-brief
behavior is covered by `DesktopApp.test.tsx`. Run `bun run check` before
publishing and disclose baseline failures separately.
