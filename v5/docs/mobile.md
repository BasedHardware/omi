# Mobile app (iOS / Android)

Mobile surfaces live in the shared React Native tree and render from the same
`AppOrchestrator` as desktop — see [`react-native/AGENTS.md`](../react-native/AGENTS.md)
for the tree map and build/test commands, and
[auth-and-sessions.md](auth-and-sessions.md) for sign-in flows and the native
transport contract.

## File map

- `src/mobile/MobileAppSurface.tsx` — shell: bottom destinations, Home,
  routing into pages.
- `src/mobile/MobileChat.tsx`, `MobileOmnibar.tsx`, `mobileTokens.ts`.
- `src/pages/` — Conversations, Memories, Tasks, Settings, Connectors.
- `src/app/AppOrchestrator.tsx` — retains requests, drafts, chat history,
  and scroll-follow state across surface switches.
- `src/app/routes.ts` — `resolveInitialRoute` over the route set.
- `src/app/useTaskMutations.ts` + `src/taskMutationClient.ts` — task writes.
- `src/app/DeviceControls.tsx`, `DeviceSession.tsx`, `useNativeDevices.ts` —
  device connection state and controls.

## Shell and navigation

- On compact screens `MobileAppSurface` owns four bottom destinations: Home,
  Conversations, Tasks, Settings; selection highlights both icon and label.
  Apps opens from Settings and keeps Settings selected, with a Back to
  Settings control. The shell has no large page headings.
- The composer defaults to Search, with accessible Ask/Search icons inline to
  the left of the shared input. Its backing area is transparent and the
  rounded field is translucent. Non-interactive gradients blend the
  scrolling content into the page background at both edges; they never cover
  the composer or navigation.
- Mobile has no phone shortcut or Live voice button: `MobileOmnibar`
  contains Ask/Search only. Desktop voice is unchanged. Capture status
  appears only while a capture is active.
- Ask and Search share one draft: Ask opens chat without remounting the
  input; closing chat restores the previous page; Search submits to Home's
  loaded-data results without sending a message. On Conversations, Search
  filters the loaded library in place — there is no duplicate top search
  field.

## Home, Tasks, Conversations

- Home groups up to three open action items with available due dates and
  owners, followed by recent conversation summaries and dates, in compact
  neutral panels without row dividers. See all and the Tasks tab open the
  full action-items list (including completed items, edits, and pagination)
  with Tasks selected. Saved memories appear in matching loaded-data Search
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
  Loading and failed reads never claim an empty timeline.
- Conversation detail keeps its Back control outside scrolling content and
  preserves the active search and All/Starred filter when returning to the
  list. Clearing search preserves Starred; Clear filters resets both.
- `MobileChat` keeps its Close control outside the message scroll region.
  Device details expand without unmounting pending device controls.

## Recording upload

Recording creation and indexed uploads retry transient failures without
duplicating sessions or packets; exhausted recovery remains visible instead
of silently completing partial audio. The encrypted journal behind this is
specified in [native-recording-journal.md](native-recording-journal.md).

## Local layout review

For layout-only review without a device, run the PWA design preview
(`bun run pwa:dev`, then `/design-preview.html?surface=mobile&data=example`)
— see [pwa.md](pwa.md). It renders the real `MobileAppSurface` with labelled
simulated states; browser previews do not verify native permissions,
Bluetooth, safe areas, or the software keyboard. Physical-device verification
remains required.
