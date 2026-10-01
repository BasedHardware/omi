# Mobile app (iOS / Android)

Mobile surfaces live in the shared React Native tree and render from the same
`AppOrchestrator` as desktop — see [`react-native/AGENTS.md`](../react-native/AGENTS.md)
for the tree map and build/test commands, and
[auth-and-sessions.md](auth-and-sessions.md) for sign-in flows and the native
transport contract.

## File map

- `src/mobile/MobileAppSurface.tsx` — shell: bottom destinations, Home,
  routing into pages.
- `src/mobile/MobileChat.tsx`, `MobileOmnibar.tsx`.
- `src/mobile/MobileTheme.tsx` — System / Light / Dark appearance and the
  `OmiThemeProvider` for every mobile surface; `MobileList.tsx` — grouped
  surfaces, the one mobile row shape, segmented control, inline states;
  `mobileDates.ts` — day headers and row times.
- `src/pages/` — Conversations, Memories, Tasks, Settings, Connectors.
- `src/app/AppOrchestrator.tsx` — retains requests, drafts, chat history,
  and scroll-follow state across surface switches.
- `src/app/routes.ts` — `resolveInitialRoute` over the route set.
- `src/app/useTaskMutations.ts` + `src/taskMutationClient.ts` — task writes.
- `src/app/DeviceControls.tsx`, `DeviceSession.tsx`, `useNativeDevices.ts` —
  device connection state and controls.

## Shell and navigation

- On compact screens `MobileAppSurface` owns four icon-only bottom
  destinations whose accessible labels are Home, Conversations, Tasks and
  Settings; the selected icon is ink, the others tertiary ink, with no pill
  behind them. Apps opens from Settings and keeps Settings selected, with a
  Back to Settings control. The shell has no large page headings.
- Every mobile surface reads the Omi design language
  ([design-language.md](design-language.md)) from `useOmiTheme()`. Settings
  offers Appearance: System (follows the OS), Light or Dark. The web build
  keeps the choice in local storage; the phone shells keep it for the app
  process until a native preference store exists.
- The composer defaults to Search, with accessible Ask/Search icons inline to
  the left of the shared input. Its backing area is transparent and the
  rounded field is translucent. Non-interactive gradients blend the
  scrolling content into the page background at both edges; they never cover
  the composer or navigation.
- Mobile has no phone shortcut or Live voice button: `MobileOmnibar`
  contains Ask/Search only. Desktop voice is unchanged. Capture status
  appears only while a capture is active.
- Ask and Search share one draft on the parent page. Ask opens a pushed Chat page with a bottom Ask-only composer; Back restores the previous page and its mode while retaining conversation history. Search submits to Home's loaded-data results without sending a message. On Conversations, Search
  filters the loaded library in place — there is no duplicate top search
  field.

## Home, Tasks, Conversations

- Home shows up to three open tasks with available due dates and owners,
  then recent conversation summaries, each list a grouped surface with
  hairline separators under a quiet section label (Tasks, Recent
  Conversations) with See All. See All and the Tasks tab open the full task
  list (To Do, then Done, with edits and pagination) with Tasks selected. Saved memories appear in matching loaded-data Search
  results, not as a Home shortcut.
- Task completion, reopening, and description edits go through the ratified
  service-binding route. Writes require a current account epoch and
  revision; missing authority leaves tasks read-only. Ambiguous retries
  reuse the same native-generated write identity, and conflict refreshes
  preserve typed drafts. Production task authority still needs provisioning.
- Task lists expose Load more, using the server cursor without combining
  different account epochs. A stale cursor refreshes the first page once;
  mutation refreshes and account changes retire pending pages. Search covers
  only loaded tasks; pagination retains at most 10,000 items.
- The shared Conversations page reads the ratified cursor envelope and
  offers Load more. It refreshes on entry, on foreground, and every 15
  seconds while active — including after a failed read; there is no manual
  Refresh button. Refresh pauses during reads, in detail, and away from the
  top of the list. Loading older pages pauses automatic refresh until you
  leave and reopen Conversations, preserving those rows. Pages append
  without duplicate IDs; a stale cursor triggers one fresh first-page read
  that replaces prior rows; failed recovery stays explicitly retryable.
  Refresh, account changes, and unmount retire pending page results.
  Loading and failed reads never claim an empty timeline; a failed read also
  offers Try Again. On mobile, day headers read Today, Yesterday or
  "Wed, Sep 23" and rows under them show only the time.
- Conversation detail keeps its Back control outside scrolling content and
  preserves the active search and All/Starred filter when returning to the
  list. Clearing search preserves Starred; Clear filters resets both.
- `MobileChat` keeps its Back control outside the message scroll region. The tab bar is hidden on the pushed Chat page; failed rows can retry, and long threads expose Jump to Latest. See [chat-ux.md](chat-ux.md).
  Device details expand without unmounting pending device controls.

## Recording upload

Recording creation and indexed uploads retry transient failures without
duplicating sessions or packets; exhausted recovery remains visible instead
of silently completing partial audio. The encrypted journal behind this is
specified in [native-recording-journal.md](native-recording-journal.md).

## Local layout review

For layout-only review without a device, run the PWA design preview
(`bun run pwa:dev`, then `/design-preview.html?surface=mobile&data=example`)
— see [pwa.md](pwa.md). Add `appearance=light` for the light scheme and
`frame=390` to pin the phone frame to a width (the visual audit does this;
headless Chrome never lays out narrower than 500 px). It renders the real `MobileAppSurface` with labelled
simulated states; browser previews do not verify native permissions,
Bluetooth, safe areas, or the software keyboard. Physical-device verification
remains required.
