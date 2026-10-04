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
| Conversations | Basic summary/transcript reader, transcript-text edit | Full detail page, playback/timeline following, summary/title/speaker/photo edits, calendar and sharing sheets |
| People | Search, filters, pinning, confidence evidence, selection/cleanup, rename/create, voice samples, conversation history | Physical voice-sample playback confirmation |
| Folders | Create/edit with explicit Save and discard guard, icon/color picker, move and delete | Bulk library selection that opens the folder picker |
| Tasks | Lists, search, completion, menus and guarded create/edit | Hierarchy, day view, selection and reorder |
| Memories | Lists, search, guarded edit, category/collection/device filters and bulk management | List selection, Mind Map and graph export |
| Chat | Transcript/composer, send/retry/follow, scoped context, voice controls/waveform, attachment/app picking | Structured interactive blocks and full attachment viewers |
| Apps | Catalog/detail, permission disclosures, enable/disable/subscribe, review editor | Owner add/edit, gallery, Markdown setup, MCP setup and specialized filters |
| Settings | Root navigation/search, profile, appearance, notifications, language, privacy, permissions, recording groups | Specialized developer, import/export, wrapped and detailed usage surfaces |
| Integrations | Task services, Apple Health connection/disconnection | Shortcuts and custom transcription parent/setup |
| Transcription tools | Vocabulary and JSON editor | Custom STT/provider setup and large JSON configurations above the preview input bound |
| Billing | Current plan selection/management and existing checkout actions | Specialized payment/referral surfaces; checkout/OAuth continue through their native SDK owners |
| Devices | Settings and diagnostics, live battery/signal charts, disconnect history/export | Discovery, storage/sync/OTA and advanced firmware controls |
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
- [ ] Full native journeys cover conversation playback/editing, graphs, device setup, calls and app-owner tools.
- [ ] The final signed Release artifact is installed over the existing iPhone identity and its saved session/data checked.
- [ ] Physical screenshots verify the final main flows and accessibility settings on the connected phone.
- [ ] Maintainer migration-direction review and full upstream mobile CI are complete.

Verification commands and containment/session rules are in [the native UI guide](ios-native-ui.md).
