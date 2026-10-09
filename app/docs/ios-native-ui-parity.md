# iOS presentation parity

Tracking: [#20426](https://github.com/BasedHardware/omi/issues/20426),
[PR #20440](https://github.com/BasedHardware/omi/pull/20440).
The opt-in preview is a staged migration. A checked item means its declared presentation
has moved; it does not mean that live backend and physical recording tests were performed.
Existing service owners remain authoritative.

| Area | Native presentation implemented | Remaining or intentionally classic |
|---|---|---|
| Main navigation | Native system Home/Tasks/Memories/Apps/Settings tabs, lazy retained pages, root-safe Settings/Memories chrome and Home/deep-link selection | Physical navigation screenshots remain deferred; Simulator evidence is used |
| Home | Complete Home chrome, capture card/status/actions, notices, recap carousel, dated conversations, local recording entry points, live capture and processing pages, record/listening/problem sheets | Upstream's Review entry card (merged October 8) is not on native Home yet |
| Library/search | Paging, scopes, folders/starred, recent searches, bulk select with merge/delete/move, row menus, day list, date filter, People results, Places map and cluster chooser, recap journey/memories-learned/stats | Interactive MapKit maps (static images and Maps hand-off by design) |
| Conversations | Full detail reader, partial-recording badge, rich summary/transcript, playback/scrub/waveform, follow/search, editors, speaker review, earlier voice matches, transcript notice, feedback/template/visibility/share sheets, test prompt page, calendar/recording sheets, photo paging/zoom/share | Upstream entity pages; physical audio confirmation |
| Recordings | Recording-file detail (transfer, playback, info, share, delete) and local recording sheet on the existing sync player | Physical device-transfer confirmation |
| People | Search, filters, pinning, confidence evidence, selection/cleanup, rename/create, voice samples, conversation history | Physical voice-sample playback confirmation |
| Folders | Create/edit with explicit Save and discard guard, icon/color picker, move and delete, bulk move from library selection | |
| Tasks and Goals | Lists, search, completion, menus, guarded create/edit, dated Tasks, project grouping, cascade selection with bulk delete/export, indent/outdent, reorder, due-date moves, collapsible sections, swipe actions; Goals page/form with progress levels; accept shared tasks | |
| Memories | Lists with review/use/revert/open conversation, search, filters, bulk management, banners and empty states, Mind Map card, Memory Graph page with selection/share | Upstream Review questions and Recent changes pages |
| Chat | Transcript/composer, send/retry/follow, scoped context, voice, attachments/app picker, rich Markdown replies with whitelisted links, structured blocks, citations, bar/line charts, activity timeline, memory review, feedback sheet | Viewers for historical non-image attachments and QuickLook (neither exists in Flutter; no stored copy) |
| Apps | Catalog/detail, reviews list/filter/owner reply, app options, capability/category pages, permission disclosures, enable/disable/subscribe, owner add/edit/confirmation, one-time API keys, gallery, Markdown/MCP setup, filters, AI app generator, payouts, Stripe Connect setup | App web home (WKWebView); Stripe onboarding in the browser |
| Settings | Root navigation/search, profile/name, appearance, notifications, language, privacy, permissions, recording groups, assistant voice, conversation timeout, developer root/webhooks/API and MCP keys/debug logs, export, fair use, import, usage, Wrapped 2025 | Referral web page |
| Integrations | Task services, Apple Health connection/disconnection, App Shortcuts link on builds that report `shortcuts_link` | Stable-toolchain builds keep the classic Data & Privacy page for the Shortcuts card |
| Transcription tools | Vocabulary, custom STT/provider setup, guarded replacement key input and explicit reveal, language/model/request/schema configuration, JSON editor up to 262,144 text units, import configuration | Configuration exceeding the bounded native editor remains on the complete original screen |
| Billing | Plan selection/management, downgrade and annual-switch confirmations, cancel-subscription and delete-account flows, usage/freemium sheets | Checkout/customer-portal web view keeps its navigation owner; dormant training-data opt-in |
| Devices | Discovery/pairing, Apple Watch and Ray-Ban Meta setup, connection guide, Bluetooth guidance, device settings with level controls, diagnostics and support tickets, firmware update/pre-flight/OTA/flash, Offline Sync pages, storage sheets and confirmations, synced conversations | Physical pairing, OTA and transfer confirmation |
| First run | Auth, consent, name, language, acquisition survey, permissions, guided voice, knowledge graph step, interactive device tutorial, step navigation and completion, announcements, feature screens, What's New, upgrade/rating prompts, permissions interstitial, language sheet | Signed-out welcome video; decorative tutorial animations |
| Calls | Setup disclosure, country/phone entry, verification status/retry, verified caller-ID management, contacts/search/permission states, dialer/DTMF and active-call controls/transcript/audio routes; existing native call engine retained | Physical call/audio-route verification |
| Shared feedback | System confirmations/action menus, guarded input sheets, presentation outcomes and dismiss signals, blocking activity HUD, toasts, one-time secret sheet | Crash and startup-failure screens |

## Completion checks

- [x] The bridge carries presentation data and whitelisted commands, never app-auth credentials; third-party STT credentials only enter native presentation during explicit credential/config editing or reveal, and new one-time keys only in the sensitive secret sheet.
- [x] Existing backend, BLE, recording, recovery, upload, checkout and permission owners remain in place.
- [x] Explicit Save/cancel/discard semantics remain available; rapid text edits are drained before Save.
- [x] Account-session changes invalidate native private content, temporary sheets, toasts, activity and secret sheets.
- [x] Invalid rows, rejected snapshots and unsupported controls restore the complete existing surface, including onboarding navigation.
- [x] Every route in the migration plan has native presentation with its existing actions reachable; intentional exclusions are listed above and in [the native UI guide](ios-native-ui.md).
- [ ] Screens merged from upstream on October 8 (Review entry, Review questions, Recent changes, entity pages) have native presentation.
- [x] Simulator production-host checks cover conversation playback/read/edit ownership, speaker selection, media paging/cleanup and advanced form validation.
- [ ] The 21 per-area host targets pass together on a Simulator against the integrated head.
- [ ] Physical playback, pairing/OTA, transfer and call/audio-route checks.
- [x] A signed Release-prod build of the integrated head is installed over the existing iPhone identity; saved account, appearance, onboarding and pendant pairing passed fresh preservation checks.
- [ ] Physical screenshots verify the final main flows and accessibility settings on the connected phone (deferred at the user's request; Simulator UI evidence is used).
- [ ] Maintainer migration-direction review and full upstream mobile CI are complete.

Verification commands and containment/session rules are in [the native UI guide](ios-native-ui.md).

October 9 integration: all eight bridge primitives and 21 area batches with their review fixes,
upstream main from October 8, Tasks project grouping and two presentation polish passes. Before the
upstream merge the full hermetic Flutter suite passed 5,559 tests (14 declared skips) plus 138
startup checks, and the analyzer ratchet found nothing new. After it, the native UI tests and every
test importing the Tasks changes passed (686). The polished SwiftUI Preview suite passed 81 of 83 UI
tests in a three-way parallel run; the two load-sensitive cases (reorder coordinates and the level
drag) passed on rerun. Ruby contracts, SwiftLint and the 42-check repository preflight passed.

Earlier batches (October 4) passed 4,622 hermetic Flutter checks, 138 startup checks, 23
software-journey checks, 24 real Flutter/UIKit host scenarios across the conversation/advanced and
Settings/Offline Sync runs, and 33 distinct native fixture scenarios. Their host runs caught and
fixed a photo loading-task identity loop, a missing chart label and a ring-storage read outside the
firmware gate. Interactive agent-flutter inspection of the synthetic local-dev host covered the new
routes; loopback failures exercised error paths only. Physical playback, calls and screenshots and
full upstream mobile CI remain unverified; skipped mobile lanes require a maintainer to apply
`ci:full` and rerun.
