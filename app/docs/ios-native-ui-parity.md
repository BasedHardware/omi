# iOS presentation parity

Tracking: [#20426](https://github.com/BasedHardware/omi/issues/20426),
[PR #20440](https://github.com/BasedHardware/omi/pull/20440).
The opt-in preview is a staged migration. A checked item means its declared presentation
has moved; it does not mean that an entire feature group is finished or that live backend
and physical recording tests were performed. Existing service owners remain authoritative.

| Area | Native presentation implemented | Presentation still to migrate |
|---|---|---|
| Home | Complete Home chrome, capture status/actions, notices, recaps, dated conversations, local recording entry points | Detailed capture flows and bulk library selection |
| Library/search | Paging, scopes, folder/starred lists, recent searches, recap browsing | Advanced selections and conversation map |
| Conversations | Full detail reader, rich summary/transcript, playback/scrub/waveform, follow/search, title/summary/transcript/speaker editors, calendar/recording sheets, lazy photo paging/zoom/share | Specialized feedback/review sheets and earlier-match chooser; physical audio confirmation |
| People | Search, filters, pinning, confidence evidence, selection/cleanup, rename/create, voice samples, conversation history | Physical voice-sample playback confirmation |
| Folders | Create/edit with explicit Save and discard guard, icon/color picker, move and delete | Bulk library selection that opens the folder picker |
| Tasks | Lists, search, completion, menus, guarded create/edit and dated Tasks with original paging/retry | Hierarchy, selection and reorder |
| Memories | Lists, search, guarded edit, category/collection/device filters and bulk management | List selection, Mind Map and graph export |
| Chat | Transcript/composer, send/retry/follow, scoped context, voice controls/waveform, attachment/app picking | Structured interactive blocks and full attachment viewers |
| Apps | Catalog/detail, permission disclosures, enable/disable/subscribe, review editor, owner add/edit/confirmation, gallery, Markdown setup, MCP setup and filters | Secure API-key creation/reveal, AI generator and specialized payout screens |
| Settings | Root navigation/search, profile, appearance, notifications, language, privacy, permissions, recording groups, developer root/webhook forms, export progress/cancel, fair-use status | Secure developer credentials, import, wrapped and detailed usage surfaces |
| Integrations | Task services, Apple Health connection/disconnection | Shortcuts and custom transcription parent/setup |
| Transcription tools | Vocabulary and JSON editor | Custom STT/provider setup and large JSON configurations above the preview input bound |
| Billing | Current plan selection/management and existing checkout actions | Specialized payment/referral surfaces; checkout/OAuth continue through their native SDK owners |
| Devices | Settings and diagnostics, live battery/signal charts, disconnect history/export, phone/cloud storage preferences | Discovery, offline storage/sync/OTA and advanced firmware controls |
| First run | Auth, consent, name, language, acquisition survey, permissions, guided voice prompts/review/receipts, step navigation and completion | Knowledge graph and interactive pendant setup |
| Calls | Setup disclosure, country/phone entry, verification status/retry, verified caller-ID management, contacts/search/permission states, dialer/DTMF and active-call controls/transcript/audio routes; existing native call engine retained | Physical call/audio-route verification |
| Shared feedback | System confirmations/action menus and guarded native input sheets | Specialized legacy dialog widgets and transient feedback presentation |

## Completion checks

- [x] The bridge carries presentation data and whitelisted commands, never auth credentials.
- [x] Existing backend, BLE, recording, recovery, upload, checkout and permission owners remain in place.
- [x] Explicit Save/cancel/discard semantics remain available; rapid text edits are drained before Save.
- [x] Account-session changes invalidate native private content and temporary input sheets.
- [x] Unsupported controls restore the complete existing surface, including onboarding navigation.
- [ ] Every remaining production route above has native presentation with its existing actions reachable.
- [x] Simulator production-host checks cover conversation playback/read/edit ownership, speaker selection, media paging/cleanup and advanced form validation.
- [ ] Native journeys cover the remaining graphs, device setup and secure credential tools; physical playback/call checks remain.
- [x] The conversation/advanced-screen Release artifact is installed over the existing iPhone identity; saved account, appearance, onboarding and pendant pairing passed fresh preservation checks.
- [ ] Physical screenshots verify the final main flows and accessibility settings on the connected phone. The read-only installed-app check is prepared, but the phone locked before it could run.
- [ ] Maintainer migration-direction review and full upstream mobile CI are complete.

Verification commands and containment/session rules are in [the native UI guide](ios-native-ui.md).

October 4 conversation/advanced-screen verification: 4,620 hermetic Flutter checks
plus 138 startup checks, 23 software-journey checks and 19 real Flutter/UIKit host
scenarios across two passing runs (plus both teardowns). All 33 distinct native
fixture scenarios passed across combined/focused runs; the combined run’s single
accessibility-server failure passed in isolation. The photo gesture test caught
and fixed a loading-task identity loop, then passed double-tap/pinch/pan/reset.
After separating the native playback projection from its existing player owner,
all 30 playback regression checks passed and normal commit/push gates passed.
The personal Release app opened normally with no failed startup stages or new
preference quarantines. Full upstream mobile CI remains maintainer-gated.
