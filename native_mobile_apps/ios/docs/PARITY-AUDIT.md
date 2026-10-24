# Parity audit: Flutter app vs native app (2026-10-08)

Three read-only audits compared every user-visible feature of the Flutter app (`~/CODING/omi-fresh/app`)
with the native app, checked in code (not taken from docs/PARITY.md). 349 features in total.

| Slice | Full | Partial | Missing | Dropped on purpose | Native only |
|---|---|---|---|---|---|
| Settings, account, plans, people, device settings | 74 | 15 | 17 | 6 | 4 |
| Conversations, detail, capture, chat, memories, tasks, search | 74 | 18 | 17 | 3 | 5 |
| Device, offline sync, capture engine, notifications, platform, app store, onboarding | 63 | 21 | 19 | 6 | 3 |
| **Total** | **211** | **54** | **53** | **15** | **12** |

## Why Flutter has about 4x more code
- Hardware we do not support: Limitless, OmiGlass, Ray-Ban Meta, Plaud, Bee, Fieldy, Friend (about 7k lines).
- Three offline-storage protocols instead of one, and duplicate sync pages for two firmware generations.
- Dropped features: Wrapped 2025, AI app generator, app creation and payouts (about 12k lines).
- Hand-built UI that SwiftUI provides (player, dialogs, charts, pickers, web views).
- Analytics, telemetry and debug probes (about 10k lines; 270+ analytics calls), Android branches.
- A second Swift Bluetooth/mic stack under Flutter plus generated platform-channel glue (about 8k lines).
- Verbose widget trees (about 6k bracket-only lines in settings alone).
- Real gaps account for a smaller share; they are listed below and in the detailed tables.

## Docs that were wrong
- docs/PARITY.md marks Live Activity, widgets, Watch app and image notifications as missing: all exist.
- docs/PARITY.md marks auto-remove of synced recordings as done: no code for it.
- Conversation search is labelled "transcript or summary" but searches the transcript only.


---

# Parity audit: conversations, home, chat, memories, tasks, goals, search (Flutter → native)

Read-only audit, 2026-10-08. Flutter: `~/CODING/omi-fresh/app/lib`. Native: `~/CODING/omi-native`.
Native paths are under `Packages/OmiFeatures/Sources/` unless they start with `App/`, `Extensions/`
or name a store (`Packages/OmiService/Sources/OmiService/Stores/`) or endpoint
(`Packages/OmiNetwork/Sources/OmiNetwork/Endpoints/`). Every status was checked in code (keys, API
paths, views), not taken from docs/PARITY.md. Where the code disagrees with PARITY.md, the Notes say so.

Method: listed user-visible features per Flutter file (l10n keys used, menu items, API calls in
`backend/http/api/*`), then grepped native for the same API path, l10n key or view. Flutter API
functions with no UI caller are reported under "Why Flutter is bigger" (dead code), not as gaps.

| Area | Feature | Flutter file | Native status | Native evidence (file) | Notes |
|---|---|---|---|---|---|
| Conversations list | Day-grouped list, paging, pull to refresh | pages/conversations/conversations_page.dart | FULL | TodayFeature/ConversationList.swift, ConversationsStore.swift | |
| Conversations list | Processing / failed-summary row with Retry, reprocess | widgets/conversation_list_item.dart | FULL | OmiComponents/ConversationRow.swift, ConversationList.swift menu (`reprocessConversation`) | |
| Conversations list | Star / unstar, starred filter | conversation_actions.dart | FULL | ConversationList.swift:110, ConversationsFeature/SearchFilters.swift | |
| Conversations list | Delete with undo | conversation_list_item.dart (swipe) | FULL | ConversationList.swift:135 `deleteWithUndo`, OmiComponents/ConversationToasts.swift | Long-press menu, not swipe: ConversationList.swift:100 says swipe fights the tab pager (on purpose). PARITY.md still says "swipe left" |
| Conversations list | Multi-select: bulk delete, move, merge (with "cannot be merged" check) | widgets/merge_action_bar.dart, merge_confirmation_dialog.dart | FULL | TodayFeature/SelectionBar.swift (`nativeMergeNotReady`, `nativeMergeNeedsTwo`) | |
| Conversations list | Folders: create, rename, delete, move, remove from folder | widgets/create_folder_sheet.dart, folder_options_sheet.dart, move_to_folder_sheet.dart | PARTIAL | OmiComponents/FolderSheets.swift, ConversationsStore+Folders.swift | An edit carries the folder's icon, color and description through to the backend (`FolderDraft`, `updateFolder`), and a deletion hands the folder's conversations to another folder (`deleteFolder(_:moveTo:)`). The sheet itself still edits the name only, so nothing in the app sets a *new* icon, color or description |
| Conversations list | Folder filter (tabs) | conversations_page.dart | FULL | TodayFeature/ConversationListExtras.swift (Home filter menu) | |
| Conversations list | One-day page (prev / next day, calendar) | day_conversations_page.dart | FULL | ConversationListExtras.swift `DayConversationsScreen` | |
| Conversations list | Conversation map | conversation_map_page.dart | FULL | TodayFeature/ConversationMapScreen.swift | |
| Conversations list | Show short / discarded conversations | (conversation display settings) | FULL | ConversationListExtras.swift `DisplayOptionsMenu`, ConversationsStore+Display.swift | |
| Conversations list | Locked row, Upgrade to Unlimited | conversation_list_item.dart | FULL | ConversationListExtras.swift `LockedRowCover` | |
| Conversations list | "New" badge on an unseen conversation | conversation_list_item.dart (`conversationNewIndicator`) | MISSING | none | Low impact |
| Conversations list | Capture gaps: calendar meetings Omi did not capture ("n conversations not captured") | capture_gaps_controller.dart, widgets/capture_gap_list_item.dart (`GET v1/calendar/capture-gaps`) | PARTIAL | APIClient+ConversationContent.swift `captureGaps`, OmiCore/Models/ConversationContent.swift `CaptureGap` | The call and its model are there; nothing draws the list yet |
| Conversations list | Daily recaps: rows, recap detail, write recap | widgets/daily_summaries_list.dart, daily_recaps_page.dart, home/widgets/home_daily_recaps.dart, daily_summary_card.dart | PARTIAL | TodayFeature/DailyRecaps.swift (`RecapRow`, `RecapScreen`), APIClient+Edits.swift | No delete recap (`deleteRecap`); no standalone recaps list page (search has a Recaps filter instead) |
| Home | Capture recovery banner | widgets/capture_recovery_banner.dart | FULL | TodayFeature/CaptureRecoveryBanner.swift | |
| Home | Live capture card: source, pause / resume, open live transcript, phone call | widgets/live_capture_card.dart | FULL | TodayFeature/TodayScreen.swift `LiveBar`, LiveTranscriptSheet.swift | |
| Home | Capture state copy: reconnecting, phone / pendant storage almost full, transcribe-later storage full, processing taking longer, pendant paused during call | widgets/processing_capture.dart (848 lines) | PARTIAL | TodayScreen.swift `LiveBar` (`nativeRecordingToPhone`, `nativeCaptureFailed`, `nativeSavingConversation`, `nativeProcessing`) | No storage-full or reconnecting states in the UI |
| Home | "Who is this?" speaker prompt card (play clip, is this you / person, not a person, save voices) | widgets/speaker_tag_prompt_card.dart (984 lines) | FULL | TodayFeature/SpeakerPromptCard.swift, OmiComponents/SpeakerNamePicker.swift, VoicesStore.swift | |
| Home | Header sync button with waiting-recordings badge | home/widgets/header_sync_button.dart | FULL | App/HomeChrome.swift:36 (`sync.hasPending`) | |
| Home | Device pill, Record with… (phone / Omi / Watch) | home/widgets/battery_info_widget.dart | FULL | App/HomeChrome.swift, App/RecordWithSheet.swift | |
| Home | Ask Omi bar + voice | home/page.dart (`askOmi`, `voiceMode`) | FULL | AgentFeature/OmiBar.swift, ChatComposer.swift (`nativeAskByVoice`) | |
| Home | Goals widget | widgets/goals_widget.dart | FULL | TodayFeature/GoalsCard.swift | |
| Home | For you cards, helpful / not helpful / stop these | home/widgets/home_for_you.dart | FULL | TodayFeature/ForYouRow.swift | |
| Home | iOS home-screen widgets data | home/home_widgets_publisher.dart | FULL | Extensions/OmiWidgets/HomeWidgets.swift | |
| Home | Deep links into conversations, tasks, recaps | home/home_deep_links.dart | FULL | App/DeepLinkRouter.swift | |
| Home | Tasks tab (tab switcher) | home/widgets/home_tab_switcher.dart | DROPPED-ON-PURPOSE | App/MainTabView.swift, TodayFeature/NeedsYouSection.swift | Tabs Home · Chat · Memories; tasks on Home (docs/CHAT-FIRST.md, docs/STRUCTURE.md) |
| Home | Needs you (max 5), Later, Not a task, AI tidy-up, Omi takes over, connect suggestion | none | NATIVE-ONLY | TodayFeature/NeedsYouSection.swift, TidyUpSheet.swift, ConnectSuggestion.swift, TaskConsolidation.swift, TaskTidyUp.swift | |
| Offline sync | Recordings waiting: process now, play, share, delete | conversations/sync_page.dart, auto_sync_page.dart, recording_detail/recording_detail_sheet.dart, wal_item_detail_page.dart | PARTIAL | DeviceFeature/DeviceRecordingsSection.swift, OmiComponents/PendingRecordingRow.swift, SyncStore.swift | No cancel sync, no delete all synced / pending, no ETA, no recording-details view (format, device id, size) |
| Offline sync | Auto-remove synced copies after N days | auto_sync_page.dart (`autoRemoveSyncedCopies*`) | MISSING | none (no key, no code in SyncStore / OfflineRecordings) | PARITY.md claims ✅ "auto-remove": not in code |
| Offline sync | Synced conversations result page (new / updated / processed) | synced_conversations_page.dart | MISSING | none | |
| Offline sync | Device storage card, download meter | widgets/device_storage_card.dart, device_download_meter.dart | FULL | DeviceRecordingsSection.swift (`deviceStorage*`) | |
| Offline sync | Store audio on phone / private cloud copy | local_storage_page.dart, private_cloud_sync_page.dart | FULL | SettingsFeature/PrivacyScreen.swift (`nativeKeepOnPhone`, `nativeStoreRecordings`) | |
| Detail | Summary / Transcript tabs | conversation_detail/page.dart, widgets/conversation_detail_tabs.dart | FULL | ConversationsFeature/ConversationDetailScreen.swift | |
| Detail | Rename title | conversation_detail/widgets.dart `ConversationTitleField` | FULL | ConversationDetailScreen.swift:91 | |
| Detail | Edit the summary text | widgets/summary_tab.dart (edit), conversation_detail_provider.dart `persistSummaryEdit` → `PATCH v1/conversations/{id}/summary` | FULL | APIClient+ConversationContent.swift `updateSummary`, ConversationDetailStore+Summary.swift, ConversationsFeature/ConversationSummaryView.swift | Omi's summary or one app's result is edited in place (`appID`), and the backend's two 404s are told apart: no summary yet vs no conversation |
| Detail | Structured summary, other apps' results, "Summarized by" | widgets/summary_tab.dart, widgets.dart `AppResultDetailWidget`, `GetAppsWidgets` | FULL | ConversationSummaryView.swift, ConversationMedia.swift `SummaryExtrasSection` (`nativeFromYourApps`, `nativeSummarizedBy`) | |
| Detail | Summary template: switch app, default, create custom | widgets/summarized_apps_sheet.dart, create_template_bottom_sheet.dart | FULL | SummaryTemplateSheet.swift, SummaryTemplatesStore.swift | |
| Detail | Discarded / empty summary: Summarize, Retry | widgets.dart `ReprocessDiscardedWidget`, `SummaryRetryWidget` | FULL | ConversationSummaryView.swift (`nativeSummaryFailed`), menu Reprocess | |
| Detail | Reprocess | page.dart | FULL | ConversationDetailMenu.swift:58, ConversationDetailStore.swift:51 | |
| Detail | Star, move to folder, delete | page.dart | FULL | ConversationDetailMenu.swift:46-86 | |
| Detail | Share link (private / shared), share as text, share audio | share.dart, page.dart | FULL | ConversationDetailMenu.swift:15-25, 75 | |
| Detail | Share via SMS to contacts | widgets/share_to_contacts_sheet.dart | FULL | ShareBySMS.swift | |
| Detail | Copy transcript / summary / conversation ID (dev) | page.dart | FULL | ConversationDetailMenu.swift:61-70 | |
| Detail | Search in conversation | widgets/detail_search_bar.dart (covers both tabs) | PARTIAL | TranscriptView.swift:104 | Transcript only, though the placeholder reads `searchTranscriptOrSummary` |
| Detail | Calendar: link event, open, share with attendees, unlink | widgets/calendar_event_sheets.dart | FULL | ConversationCalendar.swift, ConversationDetailStore+Extras.swift:29-67 | |
| Detail | Capture recordings: view, separate | widgets/capture_recordings.dart, capture_group_separation.dart | FULL | CaptureRecordingsSheet.swift | |
| Detail | Test prompt (developer) | test_prompts.dart | FULL | ConversationDetailMenu.swift:72, CaptureRecordingsSheet.swift `TestPromptSheet` | |
| Detail | Ask Omi about this conversation | page.dart (`ChatPageContext`) | FULL | ConversationDetailMenu.swift:36 | |
| Detail | Participants, location map, photos, meeting screenshots (open, delete), processing strip | widgets/conversation_detail_header.dart, maps_util.dart, conversation_screenshots_section.dart, conversation_activity_strip.dart | FULL | ConversationMedia.swift (`ParticipantsRow`, `ScreenshotsStrip`, `ProcessingStrip`), OmiComponents/PlaceViews.swift | |
| Detail | Full-screen photo viewer with zoom / pan | widgets/media_viewer_page.dart | PARTIAL | ConversationMedia.swift:257 `ImageViewer` | No zoom |
| Detail | "Was this helpful?" feedback | widgets/feedback_sheet.dart, feedback_prompt_policy.dart | PARTIAL | SummaryFeedbackRow.swift, SummaryFeedbackStore.swift | Summary reasons only. Missing recording reasons (missing audio, wrong speaker, poor transcription, fragmented, delayed) and "Chat with us" |
| Detail | App Store review prompt after reading a summary | widgets/app_review_prompt.dart, widgets/review_reading_moment.dart | PARTIAL | OnboardingFeature/SetupStep.swift:11 | Asked once at the end of setup only |
| Detail | Action items under the summary: check off, hand to Omi | none (Flutter shows no task list in detail) | NATIVE-ONLY | ConversationDetailScreen.swift:304 | |
| Detail | Key points, events → add to iPhone calendar, waiting on others, Ask / Check / Send to my AI | none | NATIVE-ONLY | ConversationSummaryView.swift:89-91, 161 | |
| Transcript | Speaker-labelled transcript | widgets/transcript.dart (1447), widgets/transcript_tab.dart | FULL | TranscriptView.swift, SpeakerTranscript.swift | |
| Transcript | Name a speaker: this line or whole voice, me, new person, not a person | widgets/name_speaker_sheet.dart (836) | FULL | OmiComponents/SpeakerNamePicker.swift, TranscriptSpeakersStore.swift:54 | |
| Transcript | Earlier voice matches, update summary with names | widgets/earlier_voice_matches_sheet.dart, speaker_summary_action.dart | FULL | NameSpeakerSheet.swift, SpeakerTranscript.swift:40 | |
| Transcript | Edit a segment's text | widgets/edit_segment_sheet.dart | FULL | TranscriptView.swift:71, ConversationDetailStore.swift:62 | |
| Transcript | Translations under segments ("Translated by Omi", notice) | widgets/transcript.dart (`translatedByOmi`, `translationNotice`) | MISSING | none in TranscriptView.swift | PARITY.md notes this only for the live transcript; the saved transcript lacks it too |
| Transcript | Tap a line to play from there; transcript follows playback | widgets/transcript.dart (`playFromHere`), widgets/transcript_playback_scroll.dart | MISSING | TranscriptView.swift has no link to the player | |
| Transcript | Unresolved-speakers notice | widgets/transcript_tab.dart | MISSING | none | Low impact |
| Audio | Play, pause, scrub, share audio (parts joined) | widgets/conversation_bottom_bar.dart (1470), audio_download_progress_sheet.dart | FULL | AudioPlayerBar.swift, ConversationDetailStore.swift:77-131 | Native adds playback speed |
| Audio | Waveform scrubber, "back to current" | widgets/conversation_bottom_bar.dart, waveform_section.dart, waveform_painter.dart | PARTIAL | AudioPlayerBar.swift:52 | Plain slider |
| Live capture | Full live transcript, pause / resume, finish | conversation_capturing/page.dart | FULL | TodayFeature/LiveTranscriptSheet.swift, CaptureStore.swift | |
| Live capture | Name a speaker while recording | conversation_capturing/page.dart | FULL | LiveSpeakersStore.swift | |
| Live capture | Live speaker suggestion chip ("Maya Chen?", `speaker_label_suggestion` event) | conversation_capturing/widgets/speaker_suggestion_chip.dart | MISSING | event not parsed in OmiNetwork/Listen | |
| Live capture | Carried-speaker banner | conversation_capturing/widgets/carried_speaker_banner.dart | MISSING | none | Low impact |
| Live capture | Upload / transcription status lines (offline catching up, upload retry, n of m pending) | conversation_capturing/page.dart | PARTIAL | TodayScreen.swift `LiveBar` | |
| Live capture | Processing page after stop | processing_conversations/page.dart | FULL | ConversationMedia.swift `ProcessingStrip`, ConversationDetailStore+Extras.swift:16 | |
| Chat | Streamed answers with steps, stop, retry, copy | chat/page.dart, widgets/ai_message.dart | FULL | AgentFeature/ChatParts.swift, ChatStore.swift | |
| Chat | History paging, earlier messages | chat/page.dart, providers/chat_history_state.dart | FULL | ChatStore+Thread.swift `loadEarlier` | |
| Chat | Starters, greeting by time of day | widgets/chat_starters.dart | FULL | ChatScreen+Empty.swift | |
| Chat | Attachments: photo, camera, file (limit) | widgets/files_handler_widget.dart | FULL | ChatAttachments.swift, ChatImageEncoder.swift (`v2/files`) | Native adds paste photo |
| Chat | Voice input into the composer | widgets/voice_recorder_widget.dart | FULL | ChatComposer.swift (`nativeDictate`) | |
| Chat | Chat apps / personas | widgets/chat_apps_drawer.dart | PARTIAL | ChatAppPicker.swift, ChatStore+Apps.swift | Switch only. No "Enable apps" link, no disable-app in the picker, no app greeting from `v2/initial-message` |
| Chat | Clear chat | chat/page.dart | FULL | ChatStore+Extras.swift `clearChat` | |
| Chat | Rating with reasons, share, read aloud | widgets/message_action_bar.dart | FULL | MessageActions.swift, VoicePlaybackStore.swift | |
| Chat | Follow-up chip, charts | widgets/chat_followup_chip.dart, chart_message_widget.dart | FULL | ChatParts.swift:49-63, ChatMedia.swift `ChartCard` | |
| Chat | Source citations open the conversation | widgets/components/chat_evidence_card.dart, ai_message.dart | FULL | ChatParts.swift:57 `CitationChips`, APIClient+ChatExtras.swift:14 | |
| Chat | Server content blocks: task card (complete), goal / memory / conversation links, discovery, question, agent-run status | chat/widgets/content_blocks/* (8 files, ~1000 lines) | FULL | OmiCore/Models/ChatBlock.swift, Mappers/ChatBlockMapper.swift (every kind), AgentFeature/ChatBlockCards.swift, ChatBlockKinds.swift, ChatBlockLinkCards.swift, ChatBlockTaskCards.swift, ChatDaySummaryCard.swift, ChatBlockLayout.swift | Every kind the backend emits is drawn, or kept as its synthesized line when this client does not know the type; `-omiChatDemoBlocks YES` shows one of each |
| Chat | Memory review card on an answer (right / wrong / fix) | widgets/components/memory_review_card.dart, ai_message.dart | PARTIAL | MemoryFeature/MemoryReview.swift | Review exists in Memories, not inline in chat |
| Chat | Day-summary message rendered as a recap | ai_message.dart (`MessageType.daySummary`) | MISSING | no `day_summary` handling in chat mapping | Shown as plain text |
| Chat | Ask about selected text of an answer | ai_message.dart, page.dart (`chatRemoveSelectedText`) | MISSING | AnswerMenu has copy / share / rate only | Low impact |
| Chat | Chat scoped to a conversation | page.dart (`chatScopeAbout`) | FULL | ChatComposer.swift (`nativeRemoveContext`) | |
| Chat | Offline hint, jump to latest, specific errors (quota, offline, timeout) | widgets/chat_chrome.dart, jump_to_latest_button.dart, ai_message.dart | FULL | ChatChrome.swift, ChatParts.swift:110 | |
| Chat | Search in chat, filter chips (approvals, drafts, jobs, files), running-now bar, Omi takes over, device tools | none | NATIVE-ONLY | ChatScreen+Tab.swift, ChatRunning.swift, HandOverSheet.swift, ChatStore+DeviceTools.swift | |
| Memories | List, search, category chips, add / edit / delete with undo | memories/page.dart, widgets/memory_dialog.dart, memory_edit_sheet.dart, memory_delete_undo.dart | FULL | MemoryScreen.swift, MemorySheets.swift, MemoriesStore.swift | |
| Memories | Source conversation, device provenance | widgets/memory_item.dart | FULL | MemoryCard.swift:23 | |
| Memories | Visibility per memory and all | widgets/memory_management_sheet.dart | FULL | MemoriesStore+Manage.swift:73-81 | |
| Memories | Pin as baseline | widgets/memory_edit_sheet.dart | FULL | MemoriesStore+Manage.swift:96 | |
| Memories | Right / wrong on new memories | widgets/memory_item.dart | FULL | MemoriesStore+Manage.swift:101 | |
| Memories | Memory graph, share as image | widgets/memory_graph_page.dart (1207) | FULL | OmiComponents/KnowledgeGraphView.swift, MemorySheets.swift | |
| Memories | Delete all memories | widgets/memory_management_sheet.dart | FULL | SettingsFeature/KnowledgeSummaryScreen.swift:47 | Moved to Settings › Memory |
| Memories | Filter "this device only" | widgets/memory_management_sheet.dart | MISSING | none | |
| Memories | Belief ledger: Current / History / All views, revert a superseded fact, Don't use / Allow use | widgets/memory_management_sheet.dart, memory_item.dart (`v3/memories/{id}/use`, `/revert`) | MISSING | no `/use` or `/revert` memory call | Flag-gated in Flutter (`memoryBeliefEnabled`) |
| Memories | Conflict review queue (keep earlier / keep new) | none | NATIVE-ONLY | MemoryReview.swift:89, APIClient+MemoryReview.swift (`v3/memories/review-queue`) | |
| Tasks | Buckets (overdue, today, tomorrow, later, no deadline), done section | action_items/action_items_page.dart (1307) | FULL | TasksFeature/TasksScreen.swift | Reached via Home › All tasks |
| Tasks | Create / edit with due date and time, complete, delete with undo | widgets/action_item_form_sheet.dart, task_delete_undo.dart | FULL | TaskFormSheet.swift:38, TasksStore+Undo.swift | |
| Tasks | Search | action_items_page.dart (`v1/action-items/search`) | PARTIAL | TasksScreen.swift (`nativeSearchTasks`) | Local substring match over loaded tasks, not server search |
| Tasks | Clear completed | action_items_page.dart | FULL | TaskMenus.swift:103 | |
| Tasks | Multi-select: bulk delete, export, done | widgets/task_selection_action_bar.dart | FULL | TaskSelectionBar.swift | No "select all / deselect all" |
| Tasks | Indent / outdent | action_items_page.dart | FULL | TaskMenus.swift:73-76 | |
| Tasks | Drag to reorder, drag between buckets (changes due date) | action_items_page.dart `LongPressDraggable` | MISSING | no drag in TasksFeature | PARITY.md: "no drag" |
| Tasks | Export to Todoist / Asana / ClickUp / Google Tasks / Reminders | services/action_item_export_service.dart | FULL | TaskMenus.swift:28-48, TaskAppSettingsStore.swift | |
| Tasks | Share link, accept shared tasks | widgets/accept_shared_tasks_sheet.dart | FULL | SharedTasksSheet.swift, TasksStore+Sharing.swift | |
| Tasks | One-day tasks page | action_items/day_tasks_page.dart | FULL | DayTasksScreen.swift | |
| Goals | List, create / edit / delete, progress | goals/goals_page.dart, action_items/widgets/goal_form_sheet.dart | PARTIAL | OmiComponents/GoalViews.swift, GoalsStore.swift | No icon picker (Flutter `l10n.icon`) |
| Search | Conversations (server), tasks, memories | search/global_search.dart (`v1/conversations/search`, `memory/search`, `v1/action-items/search`) | PARTIAL | ConversationsFeature/SearchScreen.swift, SearchStore.swift:187-209 | Tasks and memories are matched locally, not by the semantic server search |
| Search | Filters: starred, people, date range, recaps | global_search.dart | FULL | SearchFilters.swift | Folders on the Home filter menu, places on the map |
| Search | Recent searches | global_search.dart | FULL | SearchStore.swift:147 | |
| Search | Browse tiles with counts (`v1/search/overview`) | global_search.dart | MISSING | none | Cosmetic |
| Widgets | Apple Watch setup | widgets/apple_watch_setup_bottom_sheet.dart | FULL | App/RecordWithSheet.swift, Watch/ | |
| Widgets | Ray-Ban Meta setup and input picker | widgets/rayban_meta_setup_sheet.dart, rayban_meta_input_picker_sheet.dart | DROPPED-ON-PURPOSE | docs/PARITY.md Decisions | Other wearables left out |
| Widgets | OmiGlass OTA, OmiGlass firmware cards | home/omiglass_ota_update.dart, capture/widgets/widgets.dart | DROPPED-ON-PURPOSE | docs/PARITY.md Decisions | |
| Widgets | App update available prompt | widgets/upgrade_alert.dart (`upgrader`) | MISSING | none | Low impact on iOS |
| Widgets | Plans sheet when the Plus meter runs low | widgets/freemium_switch_dialog.dart | PARTIAL | CaptureStore.swift (freemium switch to on-device) | Switch happens; no prompt sheet |
| Widgets | Connection guide sheet | widgets/connection_guide_sheet.dart, pages/capture/connect.dart | PARTIAL | DeviceFeature/OmiHelpScreen.swift | Device audit owns this |

## Counts

117 rows: FULL 76 · PARTIAL 18 · MISSING 15 · DROPPED-ON-PURPOSE 3 · NATIVE-ONLY 5 (some
NATIVE-ONLY rows group several native features).

## Biggest gaps (ranked by user impact)

1. **Transcript and audio are not linked**: no "play from here" on a line, no transcript that follows playback; the player is a plain slider without waveform.
2. **Translations in the saved transcript**: Flutter shows "Translated by Omi" lines; native drops them (live and saved).
3. **Offline sync management**: no auto-remove of synced copies after N days, no cancel sync, no delete all synced / pending, no recording details, no "synced conversations" result page.
4. **Live speaker suggestions**: the `speaker_label_suggestion` chip ("Maya Chen?") and the carried-speaker banner during recording, and the unresolved-speakers notice on a saved one.
5. **Memory belief ledger**: Current / History views, revert a superseded fact, "Don't use" a memory, and the this-device filter (flag-gated in Flutter).
6. **Search depth**: tasks and memories searched by local substring instead of the server's semantic search; conversation search covers the transcript but not the summary.
7. **Task drag**: no reordering or dragging between buckets to change the due date (smaller: no select-all).
8. **Capture gaps**: the list of calendar meetings Omi did not capture. The call (`captureGaps`) and the model (`CaptureGap`) exist; no screen draws them.
9. **Chat day-summary and question cards**: the day-summary recap message and "ask about selected text of an answer" are not rendered (every other content block kind is).
10. **"New" badge and app-update prompt**: a conversation nobody has opened is not marked, and no prompt offers a newer build.

Smaller: a folder's icon / color / description in the editor (an edit carries all three through, but nothing
sets a new one); recording-quality feedback reasons and "Chat with us"; delete a recap; photo zoom;
chat-app enable / disable shortcut and server greeting; goal icon; review prompt after a summary;
capture state copy for storage full and reconnecting.

## Why Flutter is bigger here

Size of the slice: Flutter pages + widgets + ui = **53,586 lines** (318 files), plus the providers
the slice uses (conversation 2,030, message 1,057, memories 1,328, action items 1,315, folder 243,
home 365, chat_history_state 331, people 362 = 7,031) and their API files (3,566), about **64k**.
Native for the same capability: features 12,083 + stores 5,933 + endpoints 1,721, about **19.7k**,
so roughly 3.3x. The share of comment lines (7 % vs 6 %) and bracket-only lines (17 % vs 18 %) is about
the same in both, so the difference is not formatting; it is what each file does.

1. **Duplicate pages for the same job.** `conversations/sync_page.dart` (933) and `auto_sync_page.dart`
   (1,058) both list and manage offline recordings, one per firmware generation
   (`supportsMultiFileSync ? AutoSyncPage : SyncPage`, home/page.dart:997). Recording detail exists twice:
   `recording_detail/recording_detail_sheet.dart` (373, its header says it "Replaces the old full-page
   detail") and `wal_item_detail/wal_item_detail_page.dart` (652) still ships. Native: one
   DeviceRecordingsSection (+ PendingRecordingRow 91).
2. **Hand-built UI that SwiftUI gives for free.** `widgets/transcript.dart` 1,447 + `conversation_bottom_bar.dart`
   1,470 vs TranscriptView 295 + AudioPlayerBar 173; `chat/widgets/ai_message.dart` 1,214 vs ChatParts 174
   + MarkdownBlocks 216; `action_items_page.dart` 1,307 (custom LongPressDraggable reorder, Dismissible,
   hover-above math, selection) vs TasksScreen 225; `ui/feedback/omi_dialogs.dart` 749 (own confirm /
   opt-out / menu dialogs) vs `.confirmationDialog` / `.alert`; `memory_graph_page.dart` 1,207 (own
   painter, physics, share) vs KnowledgeGraphView 129; `speaker_tag_prompt_card.dart` 984 vs
   SpeakerPromptCard 145 + SpeakerNamePicker 139. 194 explicit `Semantics(` wrappers in the slice that
   SwiftUI `Button` / `Label` provide implicitly.
3. **Device and other-wearable code living in the slice.** pages/home holds firmware: `firmware_mixin.dart`
   407, `firmware_update.dart` 488, `firmware_update_dialog.dart` 153, `omiglass_ota_update.dart` 710
   (dropped wearable). widgets/ holds `rayban_meta_setup_sheet.dart` 220 + `rayban_meta_input_picker_sheet.dart`
   206, `bluetooth_guidance_listener.dart` 190, `connection_guide_sheet.dart` 203. About 2,600 lines that
   native keeps in DeviceFeature or does not have on purpose.
4. **Dead or unwired code.** API + provider code with no UI caller: `reorderFoldersApi` /
   `FolderProvider.reorderFolders`, `reportMessageServer`, `getGoalAdvice`, `suggestGoal`,
   `autoLinkCalendarEvent` (provider method never called), `getConversationTranscripts`, the
   conversation-detail action-item delete / undo (`deleteActionItem`, `undoDeleteActionItem`,
   `deleteActionItemPermanently` in conversation_detail_provider.dart:796-809; the detail page shows no
   task list), and chat-session list / delete / title generation in `chat_history_state.dart` (331) and
   `chat_sessions.dart` with no session picker in the UI.
5. **Test seams and race handling inside providers.** `memories_provider.dart` takes about 12 injectable
   request functions in its constructor; `chat_history_state.dart` is mostly epoch checks and
   "switch fences" for app switches; `conversation_detail_provider.dart` is 1,292 lines, `conversation_provider.dart`
   2,030. Native splits the same into small `@Observable` stores (ConversationsStore + 4 extensions,
   ChatStore + 5) and leans on structured concurrency (task cancellation instead of epochs).
6. **Telemetry inline.** 151 analytics calls (`PlatformManager.instance.analytics…`,
   `trackConversationAction`) sit in the widget code, often with a wrapper per menu item
   (conversation_detail/page.dart:535-560 maps menu ids to analytics actions). Native has none in this slice.
7. **Features native does not have** (the gaps above): the capture-gaps list, belief ledger, live speaker
   suggestions, drag reorder, translations, sync-management extras, feedback reasons, folder styling.
   Together roughly 3-4k Flutter lines.
8. **Verbose widget trees and inline styling.** 1,976 lines of `EdgeInsets` / `BorderRadius` /
   `BoxDecoration` / `TextStyle` / `copyWith` / `SizedBox`; e.g. the Home Ask bar's mic button in
   home/page.dart:870-930 nests Container → Row → GestureDetector → Semantics → Container → Container →
   FaIcon over about 60 lines; native OmiBar.swift is 41 lines for the whole bar.

---

# Parity audit: Settings, account, payments, referral, announcements, phone calls

Flutter: `~/CODING/omi-fresh/app/lib/pages/{settings,payments,referral,announcements,phone_calls}` (32,560 lines, 98 files).
Native: `~/CODING/omi-native` (`Packages/OmiFeatures/Sources/SettingsFeature` 5,464 lines + `DeviceFeature` ~1,000 lines, plus stores in `OmiService`, endpoints in `OmiNetwork`).
Method: every Flutter file opened or grepped for l10n keys, rows, dialogs and API calls; each feature checked in native code (not docs). Read-only audit, 2026-10-08.

Native paths below are relative to `Packages/OmiFeatures/Sources/` unless they start with `Packages/`, `App/` or `Extensions/`.

Statuses: FULL · PARTIAL · MISSING · DROPPED-ON-PURPOSE (docs/PARITY.md "Decisions" or code says so) · NATIVE-ONLY · N/A (dead or Android-only in Flutter).

## Table

| Area | Feature | Flutter file | Native status | Native evidence (file) | Notes |
|---|---|---|---|---|---|
| Hub | Grouped settings home, profile header (name, email, plan) | settings_drawer.dart, settings_groups.dart | FULL | SettingsFeature/SettingsScreen.swift (`ProfileHeader`, sections) | IA regrouped (Omi / How Omi helps / Connections / App / Help). Flutter "New"/"Beta" row tags not carried over |
| Hub | Settings search (65 entries) | settings_search_index.dart | FULL | SettingsFeature/SettingsSearch.swift | Opens the holding screen, same as Flutter |
| Hub | Version + copy "version (build) – device, iOS x" | settings_groups.dart (HelpAbout) | PARTIAL | SettingsScreen.swift footer `Omi \(appVersion)` | No build number, no device/OS string, no copy button (support asks for this) |
| Account | Edit name (local + Firebase display name) | change_name_widget.dart, profile.dart | FULL | SettingsFeature/AccountScreen.swift alert → `session.changeName` | |
| Account | Show email | profile.dart | FULL | AccountScreen.swift | |
| Account | Copy user ID | profile.dart | FULL | SettingsFeature/DeveloperScreen.swift (`nativeCopyUserID`) | Moved behind Help › Developer mode |
| Account | Sign out with confirm | sign_out.dart | FULL | AccountScreen.swift confirmationDialog → `session.signOut()` | |
| Account | Delete account: 3 steps (reason, free-text feedback, consequences list, Export-first row, type DELETE to confirm), error toast | delete_account.dart | PARTIAL | AccountScreen.swift confirmationDialog; Packages/OmiService/.../SessionStore.swift `deleteAccount(reason:)` | Native sends `reason: nil`, no reason_details, no type-to-confirm, no export shortcut. Failure is silent: `_ = await session.deleteAccount` and `errorMessage` is only rendered by AuthFeature/SignInScreen.swift |
| Account | Redo onboarding | – | NATIVE-ONLY | AccountScreen.swift `nativeRedoOnboarding` | |
| Plan & usage | Plan name, minutes used/limit, chat quota | usage_page.dart | FULL | SettingsFeature/UsageScreens.swift `planSection` | |
| Plan & usage | "Set up on-device for unlimited free transcription" hint when premium minutes run low | usage_page.dart (`_OnDeviceHint`) | MISSING | – | No link from quota to on-device switch |
| Plan & usage | Activity: today / month / year / all time totals + chart | usage_page.dart, widgets/usage/usage_chart.dart, usage_stat_tile.dart | FULL | UsageScreens.swift `ActivitySection` (Swift Charts) | Flutter chart annotates best day/month/year and peak hour; native chart is plain |
| Plan & usage | Share stats | usage_page.dart (RepaintBoundary → watermarked PNG) | PARTIAL | UsageScreens.swift `ShareLink(item: shareText)` | Native shares text, Flutter an image card |
| Plan & usage | Fair use: daily/weekly meters, stage (warning/throttle/restrict), resets-at, case reference | fair_use_page.dart | FULL | UsageScreens.swift `FairUseSection` | Merged into Plan & usage |
| Plans | Plan cards (monthly/yearly toggle, Popular badge, Save %, desktop access, feature bullets, hero) | widgets/plans_sheet.dart, plans/plan_cards.dart, plans_hero.dart, plan_display_name.dart | PARTIAL | UsageScreens.swift `ForEach(availablePlans) … "Upgrade to plan · price"` | Plain rows, no comparison or what-you-get copy |
| Plans | Checkout | payment_webview_page.dart | FULL | UsageScreens.swift `settings.checkoutURL` → SafariView | Native uses SFSafariViewController instead of an in-app webview |
| Plans | Manage plan / payment method (Stripe portal) | plans_sheet.dart | FULL | UsageScreens.swift `settings.portalURL()` | |
| Plans | Promo code entry + invalid-code error | plans_sheet.dart | MISSING | – | No `promotion_code` anywhere in Packages/OmiNetwork |
| Plans | Change plan / schedule annual upgrade / confirm plan change / "already scheduled" | plans_sheet.dart | MISSING | – | Native can only start a new checkout |
| Plans | Resubscribe a cancelled plan | plans_sheet.dart | PARTIAL | Packages/OmiNetwork/.../APIClient+Settings.swift:148 ("nil when reactivated in place") | Works through the upgrade rows; no explicit Resubscribe action or "set to cancel on" state beyond `nativeSubscriptionEnds` |
| Plans | Downgrade to free (freemium limits list) and switch to on-device | plans_sheet.dart | MISSING | – | |
| Plans | Training-data program opt-in for free Unlimited | widgets/plans/training_data_option.dart | N/A | – | Dead in Flutter: `_showTrainingDataOptIn = false` (plans_sheet.dart:58) |
| Plans | Cancel subscription: reason → per-reason feedback → consequences (battery, delay, speakers, phone calls) → confirm, step indicator | widgets/cancel_subscription_sheet.dart, leave_flow_widgets.dart | PARTIAL | SettingsFeature/SubscriptionAndReferral.swift `CancelSubscriptionSheet` → `DELETE v1/payments/subscription` | Same reasons + details + "ends at period end"; no consequences/retention step |
| Referral | Referral program | referral/referral_page.dart (web view of affiliate.omi.me) | FULL | SubscriptionAndReferral.swift `ReferralScreen` (`v1/users/me/referral`) | Native is richer: own link, share, copy, how it works, program page |
| Device | Header: battery, charging, connected/disconnected | settings/device/device_page_header.dart | FULL | DeviceFeature/DeviceScreen.swift | |
| Device | Live audio data rate (kbps) | device_page_header.dart | MISSING | – | Minor, debug-ish |
| Device | Device info (name, ID, model, serial, firmware, hardware rev, manufacturer) | device/device_info_groups.dart | FULL | DeviceScreen.swift `DeviceInfoScreen` | Native adds audio codec |
| Device | Firmware update | device_settings.dart (productUpdate) | FULL | DeviceFeature/FirmwareUpdateRow.swift, Packages/OmiService/.../FirmwareStore.swift | |
| Device | Roll back to latest stable firmware | device_settings.dart `_confirmRollback` | MISSING | FirmwareStore.swift:24 "No rollback, no channels" | |
| Device | Double-tap action (end / star / mute) | device/device_control_sheets.dart | FULL | DeviceFeature/DeviceControlsSection.swift | |
| Device | Mute / pause listening | device_control_sheets.dart | FULL | DeviceControlsSection.swift `device.mute` | |
| Device | LED brightness | device_control_sheets.dart | FULL | DeviceControlsSection.swift slider | |
| Device | Mic gain, 9 levels with descriptions | device_control_sheets.dart | PARTIAL | DeviceControlsSection.swift `Sensitivity` (loud=3, normal=5, quiet=7) | 3 presets; muted/max/very high not selectable |
| Device | Find device | device_settings.dart | FULL | DeviceControlsSection.swift `findDevice()` | |
| Device | Forget device (confirm) | device_settings.dart | FULL | DeviceScreen.swift | |
| Device | Unpair (Limitless BLE unpair) | device_settings.dart | DROPPED-ON-PURPOSE | docs/PARITY.md Decisions (other wearables) | |
| Device | Ray-Ban Meta: capture photo, camera/mic status | device_settings.dart, device_info_groups.dart | DROPPED-ON-PURPOSE | docs/PARITY.md Decisions | |
| Device | Auto-sync offline recordings toggle (default on) | device_settings.dart (`autoSyncOfflineRecordings`) | MISSING | DeviceFeature/DeviceRecordingsSection.swift ("syncing itself stays automatic"); key only in OmiPersistence/Preferences.swift migration list | No opt-out |
| Device | Offline sync entry (recordings on Omi, storage meter) | settings_destinations.dart → sync pages | FULL | DeviceRecordingsSection.swift | sync_page itself is outside this slice |
| Device | Device tutorial | device_settings.dart | FULL | DeviceFeature/OmiHelpScreen.swift "Learn the button again" | |
| Device | Charging issues | device_settings.dart | FULL | OmiHelpScreen.swift | |
| Device | Diagnostics: RSSI live, battery history, disconnect history, share bundle, send to support | settings/device_diagnostics.dart | FULL | DeviceFeature/DeviceDiagnosticsScreen.swift, Packages/OmiService/.../DeviceDiagnostics.swift | Bundle lacks Flutter's BLE log / extended firmware diagnostics (native host layer) |
| Listening | Spoken (primary) language, searchable list | language_settings_page.dart, language_selection_dialog.dart | FULL | SettingsFeature/CaptureSettingsScreen.swift Picker (`.navigationLink`) | No search field over ~100 languages |
| Listening | Detect languages / automatic translation | language_settings_page.dart | FULL | CaptureSettingsScreen.swift `setLanguageDetection` | |
| Listening | App language | language_settings_page.dart | FULL | SettingsFeature/AppearanceScreen.swift → iOS per-app language | Platform-idiomatic |
| Listening | Custom vocabulary add/remove/count | custom_vocabulary_page.dart | FULL | CaptureSettingsScreen.swift `VocabularyScreen` | |
| Listening | Conversation timeout (2/5/10/30 min, 4 h) | conversation_timeout_dialog.dart | FULL | CaptureSettingsScreen.swift; Packages/OmiService/.../CaptureStore.swift:109 | Same values |
| Listening | Transcribe later (+ storage-full note) | settings_groups.dart | PARTIAL | CaptureSettingsScreen.swift `ListeningAdvancedScreen` | Toggle present; no "storage full" state (no batchStorage/storageFull in native) |
| Listening | Background mode | settings_groups.dart | N/A | – | Android-only in Flutter |
| Listening | Voice profile (record your voice again) | settings_destinations.dart `openVoiceProfile` | FULL | SettingsFeature/PeopleScreen.swift (`voiceScreen`) | |
| Transcription | Source: Omi / on-device / own provider | transcription_settings_page.dart | FULL | ListeningAdvancedScreen, SettingsFeature/AdvancedTranscriptionScreen.swift | Native adds server model Omi/Parakeet |
| Transcription | Own provider: OpenAI, Deepgram, Gemini, local Whisper (host+port), custom HTTP, custom live WebSocket; key show/hide; model; language | transcription_settings_page.dart, transcription/transcription_fields.dart, stt_language.dart | PARTIAL | Packages/OmiService/.../CustomSTT/CustomSTTSettings.swift, CustomTranscriber.swift | No Gemini, no custom live WebSocket; host/port folded into one URL; key moved to Keychain (better) |
| Transcription | Import / export JSON config, provider templates, request-config and response-schema JSON editor, reset | transcription_settings_page.dart, transcription/json_editor_page.dart, transcription_dialogs.dart, transcription_sections.dart | MISSING | – | Power-user feature |
| Transcription | "Send raw audio to Omi" toggle + codec warning | transcription_settings_page.dart | PARTIAL | CustomSTTSettings.swift `json()` hardcodes `send_raw_audio_to_omi: true` | Codec warning not needed (native feeds PCM16); the opt-out is gone |
| Transcription | On-device Whisper download, RAM/old-device warnings | transcription_settings_page.dart | FULL | AdvancedTranscriptionScreen.swift `usingNativeIosSpeech`, `nativeEngineNoDownload` | Flutter iOS also uses Apple speech; the download UI is Android |
| Transcription | STT logs (live, copy) | transcription_settings_page.dart | FULL | DeveloperScreen.swift `DebugLogScreen(source: "stt")` | |
| Transcription | Premium minutes + View usage on the transcription page | transcription_settings_page.dart | FULL | UsageScreens.swift | Lives in Plan & usage instead |
| Assistant | Spoken replies off / headphones / always | voice_settings_page.dart | FULL | SettingsFeature/AssistantScreen.swift | |
| Assistant | Assistant voice list + preview (shared across devices) | voice_settings_page.dart | FULL | AssistantScreen.swift `VoicePickerScreen` | |
| Notifications | Notification frequency, 6 levels + descriptions | notifications_settings_page.dart | FULL | AssistantScreen.swift | Moved to Assistant; Notifications links there |
| Notifications | Daily summary on/off + delivery hour | notifications_settings_page.dart | FULL | AssistantScreen.swift, Packages/OmiNetwork/.../APIClient+Settings.swift:162 | |
| Notifications | Live Activity "Show on lock screen" toggle | widgets/live_activity_settings.dart | MISSING | Extensions/OmiWidgets/OmiLiveActivity.swift exists, no in-app toggle | iOS system toggle covers part of it |
| Notifications | Permission status / allow | notifications_settings_page.dart | FULL | SettingsFeature/NotificationsScreen.swift | |
| Display | Show short / discarded conversations, short threshold | conversation_display_settings.dart | FULL | TodayFeature/ConversationListExtras.swift | Moved to Home filter menu |
| Display | Appearance system / light / dark | settings_groups.dart | FULL | AppearanceScreen.swift | Native adds preview |
| People | List, search, add, rename, delete | people.dart, widgets/people_list.dart, person_name_dialog.dart, person_avatar.dart | FULL | PeopleScreen.swift | |
| People | Filters (all, low confidence, needs voice, pinned, recent) + counts / stats line | widgets/people_list.dart | MISSING | – | |
| People | Multi-select + bulk delete in the list | people.dart | PARTIAL | SettingsFeature/PeopleCleanUpScreen.swift | Bulk delete only through Clean up (unsure people) |
| People | Pin / unpin | people_list.dart, person_detail_page.dart | FULL | PersonDetailScreen.swift, Packages/OmiService/.../SettingsStore+People.swift `setPinned` | |
| People | Confidence meter + "Why this confidence" evidence sheet | widgets/person_confidence.dart | MISSING | `confidence` used only to pick clean-up candidates (SettingsStore+People.swift:26) | ~60 strings of explanation UI |
| People | Clean up unsure people | people_clean_up_page.dart | FULL | PeopleCleanUpScreen.swift | |
| People | Ignored voices + restore | widgets/ignored_voices_sheet.dart | FULL | PeopleCleanUpScreen.swift `IgnoredVoicesScreen` | |
| People | Ask to tag / remember others' voices toggles | widgets/voice_profile_settings_section.dart | FULL | PeopleScreen.swift | |
| People | Person detail: samples play/delete, talk time, last heard, conversations, rename, delete | person_detail_page.dart | FULL | PersonDetailScreen.swift | No confidence block |
| Integrations | Google Calendar, Gmail OAuth connect / disconnect | integrations_page.dart | FULL | SettingsFeature/CapabilitiesScreen.swift, Packages/OmiService/.../CapabilitiesStore.swift | |
| Integrations | Apple Health detail: connect, denied, disconnect, feature list | apple_health_detail_page.dart | FULL | SettingsFeature/AppleHealthScreen.swift | Native adds last sync + Sync now |
| Integrations | Task apps (Todoist, Asana, ClickUp, Google Tasks) connect / disconnect, default app | task_integrations_page.dart, integration_settings_page.dart, todoist/google_tasks_settings_page.dart, integration_selection_card.dart | FULL | CapabilitiesScreen.swift, SettingsFeature/TaskAppSettingsScreen.swift | |
| Integrations | Apple Reminders access | task_integrations_page.dart | FULL | CapabilitiesScreen.swift `RemindersRow` | |
| Integrations | Asana workspace/project, ClickUp workspace/space/list | asana_settings_page.dart, clickup_settings_page.dart | FULL | TaskAppSettingsScreen.swift | |
| Integrations | Trello / Monday "coming soon" | task_integrations_page.dart | N/A | – | Placeholders only in Flutter |
| Integrations | Add MCP server, Create your own app | integrations_page.dart | DROPPED-ON-PURPOSE | docs/PARITY.md Decisions (building apps) | |
| Integrations | AI app generator | ai_app_generator_page.dart, ai_app_generator_provider.dart | DROPPED-ON-PURPOSE | docs/PARITY.md Decisions | |
| Integrations | Connect your AI (Claude / ChatGPT / other MCP), guided | – (Flutter: developer_mcp_section only) | NATIVE-ONLY | SettingsFeature/ConnectAIScreen.swift | |
| Privacy | Encryption banner + Learn more | data_privacy_page.dart | MISSING | – | Informational |
| Privacy | Siri / Spotlight indexing opt-out toggle | data_privacy_page.dart (`siriIndexSetting`) | MISSING | App/System/OmiEntities.swift always indexes | Privacy-relevant |
| Privacy | Ask Omi Siri shortcut hint | data_privacy_page.dart | FULL | App/System/SiriTipSheet (Home), App Shortcuts | Different place |
| Privacy | App access list (what each app reads, triggers) | data_privacy_page.dart | FULL | SettingsFeature/PrivacyScreen.swift `AppAccessScreen` | |
| Privacy | Export all data (progress, cancel, share) | data_export.dart, data_export_files.dart | FULL | PrivacyScreen.swift `ExportDataRow`, Packages/OmiNetwork/.../APIClient+Profile.swift:10 | |
| Privacy | Permissions page: notifications, location, Bluetooth, microphone status + Enable | permissions_page.dart | PARTIAL | PrivacyScreen.swift (one row → iOS Settings, location row), NotificationsScreen.swift | No Bluetooth / microphone status in-app (Flutter's most-opened settings item) |
| Privacy | Store recordings (cloud) / audio on phone | settings groups (outside files) | FULL | PrivacyScreen.swift `nativeStoreRecordings`, `nativeSettingsAudioOnPhone` | |
| Import | Limitless zip import, jobs with status, refresh, cancel | import_history_page.dart | FULL | SettingsFeature/ImportScreen.swift, Packages/OmiNetwork/.../APIClient+Imports.swift | Native adds per-job delete |
| Import | Estimated time remaining | import_history_page.dart | PARTIAL | ImportScreen.swift (files done/total, counts) | No ETA |
| Import | Delete all imported Limitless conversations | import_history_page.dart, backend/http/api/imports.dart:155 (`DELETE v1/import/limitless/conversations`) | MISSING | – | PARITY.md calls it a backend stub; Flutter calls it and shows the count |
| Phone calls | Intro + recording consent | phone_calls/phone_setup_intro_page.dart | FULL | SettingsFeature/PhoneCallsScreen.swift | |
| Phone calls | Number setup (country search), verify by call with code + statuses | phone_setup_number_page.dart, phone_setup_verify_page.dart, payments/widgets/country_bottom_sheet.dart | FULL | SettingsFeature/PhoneNumberSetupScreen.swift | |
| Phone calls | Verified numbers, delete with confirm | settings/phone_call_settings_page.dart | FULL | PhoneCallsScreen.swift | |
| Phone calls | Dialer: keypad, contacts tab + search, paste, free-call limits | phone_calls/phone_calls_page.dart | FULL | SettingsFeature/PhoneDialerScreen.swift, PhoneCallsScreen.swift | |
| Phone calls | Active call: live transcript, mute, speaker, keypad, audio output, states | phone_calls/active_call_page.dart | FULL | SettingsFeature/ActiveCallScreen.swift, App/PhoneCalls/* | Needs device + Twilio keys to verify at runtime |
| Phone calls | Minimized active-call banner | phone_calls/active_call_banner.dart | FULL | ActiveCallScreen.swift `OngoingCallPresenter` | |
| Phone calls | Recent calls list | – | NATIVE-ONLY | PhoneCallsScreen.swift `nativePhoneRecentCalls` | |
| Announcements | What's new / changelog | announcements/changelog_sheet.dart | FULL | SettingsFeature/WhatsNew.swift `WhatsNewScreen`, Packages/OmiService/.../AnnouncementsStore.swift | |
| Announcements | Feature tours | announcements/feature_screen.dart | FULL | WhatsNew.swift `AnnouncementSheet` | |
| Announcements | Announcement dialog | announcements/announcement_dialog.dart | FULL | WhatsNew.swift `WhatsNewPresenter` | |
| Help | Help center in the app language | settings_destinations.dart (41 locales, zh→zh-CN, no→nb) | PARTIAL | SettingsFeature/PhoneAndHelpScreens.swift `helpLanguage` (13 locales) | Native sends `zh` (Flutter maps to `zh-CN`): likely broken link for Chinese |
| Help | Feedback / bug report | settings_destinations.dart | FULL | PhoneAndHelpScreens.swift | |
| Help | Intercom support chat | settings_groups.dart | FULL | SettingsFeature/SupportChatRow.swift | Only when Intercom keys are in the build |
| Help | Replay introduction, Developer mode switch | – | NATIVE-ONLY | PhoneAndHelpScreens.swift | Flutter always shows Developer settings |
| Developer | Webhooks (conversation, transcript, audio bytes + interval, day summary), discard-changes guard | developer.dart | FULL | DeveloperScreen.swift `WebhooksScreen`, Packages/OmiNetwork/.../APIClient+Developer.swift | Native adds recent events |
| Developer | Developer API keys with per-resource read/write scopes (conversations, memories, tasks, goals) | widgets/developer_api_keys_section.dart, create_dev_api_key_sheet.dart, dev_api_key_list_item.dart, dev_api_key_created_dialog.dart | PARTIAL | SettingsFeature/DeveloperKeysSection.swift (read-only / full access) | API supports `scopes:` (APIClient+Developer.swift:105), UI offers two presets |
| Developer | MCP keys, config JSON, Claude Code snippet | developer_mcp_section.dart, create_mcp_api_key_dialog.dart, mcp_api_key_*.dart | FULL | DeveloperKeysSection.swift | |
| Developer | MCP OAuth client ID for Claude Desktop connector | developer_mcp_section.dart | FULL | ConnectAIScreen.swift (Claude/ChatGPT sign in themselves) | Different UX |
| Developer | Debug log to file, share, clear, choose log file, 3-day cleanup | developer.dart | FULL | DeveloperScreen.swift `DeveloperLogsScreen`, Packages/OmiService/.../DebugLog.swift:40 | One file instead of a picker |
| Developer | VAD gate, conversation developer tools, transcription diagnostics | developer.dart | FULL | DeveloperScreen.swift | |
| Developer | Flash custom firmware zip | developer_firmware_flash_page.dart | MISSING | – | PARITY.md: waits for owner approval (not a drop) |
| Developer | Creator payouts (Stripe Connect, PayPal, country) | payments/payments_page.dart, stripe_connect_setup.dart, payment_method_provider.dart, widgets/*, models/* | DROPPED-ON-PURPOSE | docs/PARITY.md Decisions (creator payouts) | No payout code in native |
| Recap | Daily recap detail: headline, overview, highlights, decisions, conversations | settings/daily_summary_detail_page.dart | FULL | TodayFeature/DailyRecaps.swift `RecapScreen` | |
| Recap | Recap stats row, locations map + timeline, action items, unresolved questions, learnings / knowledge nuggets | daily_summary_detail_page.dart | MISSING | Packages/OmiCore/.../DailySummary.swift has no fields for them | |
| Recap | Recap share, delete, regenerate (with cooldown) | daily_summary_detail_page.dart | MISSING | – | |
| Wrapped | Wrapped 2025 page + share templates | wrapped_2025_page.dart, wrapped_2025_share_templates.dart | DROPPED-ON-PURPOSE | docs/PARITY.md "dropped by owner decision 2026-10-07" | Leftover `wrapped(year:)` / `generateWrapped` in Packages/OmiNetwork/.../APIClient+Profile.swift:84-91 can go |

Counts (rows): FULL 74 · PARTIAL 15 · MISSING 17 · DROPPED-ON-PURPOSE 6 · NATIVE-ONLY 4 · N/A 3 (119 rows).

## Biggest gaps (ranked by user impact)

1. **Delete account**: no reason/feedback sent, no type-to-confirm or export-first step, and a failed delete is silent (error only shown on the sign-in screen). Legal/trust surface.
2. **Plan changes**: no promo code, no downgrade to free / switch to on-device, no scheduled annual upgrade, plan picker is bare rows. Direct revenue and retention impact.
3. **Daily recap detail**: action items, unresolved questions, learnings, map/timeline, stats, share, delete, regenerate all missing (Home entry point, used daily).
4. **Permissions overview**: no in-app Bluetooth / microphone status (Flutter comment: most-opened Settings item, people fix mic/Bluetooth here).
5. **Spotlight/Siri indexing opt-out** missing: native always indexes conversations and memories.
6. **Cancel subscription** lacks the consequences/retention step.
7. **People confidence + filters**: no confidence meter or explanation, no low-confidence / needs-voice / pinned filters, no bulk delete outside Clean up.
8. **Device**: auto-sync opt-out, firmware rollback, 9-step mic gain (3 presets), data rate.
9. **Custom STT power features**: Gemini and live WebSocket providers, JSON import/export and schema editor, raw-audio opt-out.
10. **Smaller**: delete imported Limitless conversations, Live Activity lock-screen toggle, help-center locales (Chinese link likely wrong), version copy with device info, dev API key scopes, image share of usage stats, encryption banner.

## Why Flutter is bigger here

Flutter slice: 32,560 lines. Native counterpart: ~6,470 lines of views (SettingsFeature + DeviceFeature) plus a few thousand in stores/endpoints. Roughly 4-5x.

1. **Dropped features, ~8,000 lines (25%)**: wrapped_2025_page.dart 4,235 + wrapped_2025_share_templates.dart 1,329; ai_app_generator_page/provider 868 + 410; payments/* 1,111. All out of scope by owner decision.
2. **Dead code**: widgets/plans/training_data_option.dart 211 lines, rendered only when `_showTrainingDataOptIn` is true, a `final` set to `false` (plans_sheet.dart:58). Trello/Monday "coming soon" entries in task_integrations_page.dart. No orphaned page files: every file in the slice is imported somewhere.
3. **Dart widget-tree verbosity**: 6,218 lines (19%) contain only closing brackets/commas, plus 2,654 blank lines and 1,196 comment lines. SwiftUI `Form`/`Section`/`Toggle`/`Picker` replace hand-built `OmiSettingsGroup`/`OmiSettingsRow` trees (e.g. device_page_header.dart 174 lines for a header DeviceScreen does in a few dozen).
4. **Hand-rolled UI that iOS gives for free**: usage_chart.dart 352 (Swift Charts in native), conversation_timeout_dialog / language_selection_dialog 262 (Picker), payment_webview_page 126 (SFSafariViewController), image share with watermark rendering in usage_page.dart (~150 lines of RepaintBoundary/canvas), country_bottom_sheet, custom sheets and dialogs per page.
5. **Multi-step "leave" flows**: delete_account.dart 312 + cancel_subscription_sheet.dart 290 + leave_flow_widgets.dart 328 = 930 lines vs ~80 native (and part of that is a real gap, see above).
6. **Power-user engines native did not port**: transcription_settings_page.dart 1,547 + transcription/* 1,053 = 2,600 lines (provider templates, JSON editor, Whisper download with RAM/device checks, Android paths) vs AdvancedTranscriptionScreen 135 + CustomSTTSettings 87 + CustomTranscriber 177.
7. **Other hardware and platforms**: 52 Ray-Ban Meta / Limitless references in device_settings.dart and device_info_groups.dart; 7 `isAndroid` branches (background mode, device info, Whisper); device_diagnostics.dart 1,060 lines pulls BLE host-API extended diagnostics, RSSI streaming and BLE logs into the bundle (native 279 + 296 store).
8. **Telemetry and logging inline**: 118 `analytics.` calls and 52 `Logger.*` calls in the slice (abandon/step tracking in every leave flow, page-opened events in every destination).
9. **Defensive file plumbing**: data_export.dart 514 + data_export_files.dart 69 (temp-dir leases, stale export cleanup, share retention) vs native `exportAllData` + a `ShareLink`.
10. **Features native hasn't built yet** account for the rest: person_confidence.dart 212, people_list.dart filters (part of 598), plans_sheet.dart 959 + plans/* 817, daily_summary_detail_page.dart 886 (native RecapScreen ~90).

---

# Parity audit: device, capture, platform (Flutter → native), 2026-10-08

Scope: Flutter `app/lib/services/**`, `pages/apps/**`, `pages/onboarding/**`, `startup`, `core`, `env`, `utils`
(user-facing parts) and `app/ios` (Runner Swift, BatteryWidget, LiveActivity, ImageNotification, omiWatchApp),
against `omi-native` code (App/, Packages/*/Sources, Extensions/, Watch/). Verified by grep/reading code;
docs/PARITY.md was used as a hint only.

**docs/PARITY.md is stale in four rows**: it says ❌ for Live Activity, battery/Up next/Latest widgets, Watch app
and image notifications, but all four exist in code and are targets in `project.yml`
(`Extensions/OmiWidgets/*`, `Extensions/LiveActivityUI/*`, `Extensions/OmiNotificationService/NotificationService.swift`,
`Watch/*`, `App/WatchSession.swift`, `App/Extras/LiveActivityController.swift`, `App/Extras/WidgetPublisher.swift`).

Status: FULL · PARTIAL · MISSING · DROPPED (docs/PARITY.md "Left out on purpose" or explicit decision) · NATIVE-ONLY.
Native paths are relative to `omi-native/`; `P/` = `Packages/`.

| Area | Feature | Flutter file | Native status | Native evidence (file) | Notes |
|---|---|---|---|---|---|
| Devices | Omi scan, connect, auto-reconnect, CoreBluetooth state restore | services/devices/connectors/omi_connection.dart, ios/Runner/Ble/OmiBleManager.swift | FULL | P/OmiDevice/.../OmiDeviceManager.swift, P/OmiService/.../Stores/DeviceStore.swift | Same restore id `com.omi.ble.restore` and `btDevice` pref, so a Flutter-paired Omi reconnects after the update |
| Devices | Audio codecs pcm8/pcm16/opus/opus_fs320 | devices/models.dart, omi_connection.dart:416 | FULL | P/OmiDevice/.../OmiGATT.swift `Codec` | |
| Devices | Battery level, charging state, low-battery alert | omi_connection.dart, notifications | FULL | OmiGATT battery + OmiControls `chargingStatus`, Stores/LowBatteryAlert.swift, App/DeviceNotifications.swift | |
| Devices | Device information (model, fw, hw, manufacturer, serial) | device_connection.dart | FULL | OmiGATT, OmiControls `serialNumber`, DeviceStore | |
| Devices | Button events single/double/long/press/release, double-tap routing, push-to-talk | omi_connection.dart, capture_controller.dart | FULL | OmiGATT `ButtonEvent`, Stores/DeviceButton.swift, Stores/AskOmiStore.swift | |
| Devices | LED brightness, mic gain / mute, haptic "find my Omi", features bitmask | omi_connection.dart:1186-1290 | FULL | P/OmiDevice/.../OmiControls.swift, DeviceStore+Controls.swift, DeviceFeature/DeviceControlsSection.swift | Gated by firmware features |
| Devices | Time sync characteristic | devices/models.dart (19b10030) | FULL | OmiStorage.swift `timeSyncPayload` | |
| Devices | Accelerometer stream | omi_connection.dart:1131 `getAccelListener` | MISSING | only the feature bit in OmiControls.swift | No Flutter UI consumer either; low impact |
| Devices | Firmware OTA over MCUmgr/SMP, latest-version check | pages/home/firmware_mixin.dart, mcumgr_flutter | FULL | P/OmiDevice/.../FirmwareUpdater.swift (iOSMcuManagerLibrary), Stores/FirmwareStore.swift | |
| Devices | Legacy Nordic DFU (old DevKit firmware) | firmware_mixin.dart:240 `startLegacyDfu` (nordic_dfu) | MISSING | none | Old Friend/DevKit units cannot be updated from native |
| Devices | Firmware rollback, custom firmware zip | developer_firmware_flash_page.dart | MISSING | none | PARITY: waits for the product owner's approval |
| Devices | Offline storage, ring buffer + custody ADVANCE (fw 3.0.20+) | wals/ring_storage_sync.dart, wals/pendant_ring_custody.dart, devices/ring_protocol.dart | FULL | P/OmiDevice/.../OmiStorage.swift, Stores/SyncStore.swift, OfflineRecordings.swift | |
| Devices | Offline storage, legacy SD-card protocol (< 3.0.20, timestamp markers 3.0.16) | wals/sdcard_wal_sync.dart (1035 lines) | MISSING | none (SyncStore speaks only ring INFO/READ/ADVANCE) | Omis on older firmware lose offline sync until they update |
| Devices | Offline storage, multi-file LittleFS protocol (LIST/READ/DELETE files) | wals/storage_sync.dart (775) | MISSING | none | Same as above |
| Devices | Storage sync over WiFi | wals/wal.dart `SyncMethod { ble }` | n/a | | Already gone in Flutter (only BLE); OTA WiFi constants remain for OmiGlass |
| Devices | Limitless pendant (BLE, flash-page sync, clock drift, native drain engine) | connectors/limitless_connection.dart (2134), wals/flash_page_wal_sync.dart, ios/Runner/Limitless/* | DROPPED | docs/PARITY.md "Left out on purpose" | Limitless *import* (zip) is kept: SettingsFeature/ImportScreen.swift |
| Devices | OmiGlass (photo stream, glass OTA over WiFi) | connectors/omiglass_connection.dart, capture_controller.dart:2307 | DROPPED | PARITY decisions | |
| Devices | Ray-Ban Meta (DAT SDK audio) | connectors/rayban_meta_connection.dart, transports/rayban_meta_transport.dart, ios/Runner/RayBanMeta/* | DROPPED | PARITY decisions | |
| Devices | Plaud, Bee, Fieldy, Friend pendant, custom BLE | connectors/plaud/bee/fieldy/friend_pendant/custom_connection.dart | DROPPED | PARITY decisions | |
| Devices | Apple Watch as audio source (watch app records, relays PCM, battery) | connectors/apple_watch_connection.dart, transports/watch_transport.dart, ios/omiWatchApp/* | FULL | Watch/WatchRecorder.swift, Watch/WatchMicrophone.swift, App/WatchSession.swift, P/OmiService/.../Watch/WatchStore.swift, App/RecordWithSheet.swift | Settings "Apple Watch" status row not wired yet (STRUCTURE.md); PARITY row is stale |
| Devices | Device picker / find other devices in onboarding | onboarding/device_selection.dart, find_device/* | PARTIAL | OnboardingFeature/OmiSteps.swift `HasOmiStep`, WatchStep.swift | Omi and Watch only (follows the wearable decision) |
| Devices | Bluetooth off / unauthorized states | devices/bluetooth_readiness.dart | FULL | OmiDeviceManager `BluetoothState`, lazy CBCentralManager | |
| Devices | Connection diagnostics, send to support | device_settings, device_diagnostics | PARTIAL | Stores/DeviceDiagnostics.swift, DeviceFeature/DeviceDiagnosticsScreen.swift | No BLE/firmware logs (Flutter's native OmiCaptureHealth / OmiBleEnergyPolicy layer) |
| Capture | Phone mic → `/v4/listen` live transcript → finalize | capture/capture_controller.dart, capture_coordinator.dart, ios/Runner/PhoneMic/* | FULL | Stores/CaptureStore*.swift, P/OmiAudio/.../PhoneMicCapture.swift, P/OmiNetwork/.../Listen/ListenSocket.swift | |
| Capture | Omi wearable capture, end-conversation by double tap, star | capture_controller.dart | FULL | CaptureStore `startDevice`, `endDeviceConversation`, `toggleStar` | |
| Capture | Background recording (audio, bluetooth-central, fetch, processing, location) | ios/Runner/Info.plist | FULL | App/Info.plist `UIBackgroundModes`, App/System/BackgroundTasks.swift | |
| Capture | Audio-session interruption handling (call, Siri, route change) with resume | ios/Runner/PhoneMic/PhoneMicInterruptionMonitor.swift, PhoneMicController.swift | FULL | P/OmiAudio/.../AudioSessionMonitor.swift, P/OmiService/.../Stores/CaptureStore+Interruption.swift | The recording stays live through a call, Siri or a route change; a failed take-back keeps the words already sent or on disk |
| Capture | Pause/resume, mute that survives conversations | capture_controller.dart | FULL | CaptureStore `pause`/`resume` | |
| Capture | Conversation timeout (2/5/10/30 min, 4 h) | capture_controller.dart | FULL | CaptureStore `conversationTimeout` | |
| Capture | Location at recording start | capture/conversation_location_capture.dart, native_batch_geolocation.dart | FULL | P/OmiService/.../Location/LocationStore.swift, CoreLocationProvider.swift | |
| Capture | Stuck-capture watchdog (wedge monitor, ingress health, auto-restart) | capture/capture_wedge_monitor.dart (555), capture_ingress_health.dart | FULL | CaptureStore+Interruption.swift (health loop), CaptureStore+Recovery.swift, TodayFeature/CaptureRecoveryBanner.swift | A health probe every few seconds takes the microphone back when the engine died without a notification; the banner names the reason while it is quiet |
| Capture | Capture recovery push + banner | services/notifications.dart `capture_recovery` | FULL | P/OmiCore/.../DeepLink.swift:78, CaptureRecoveryBanner.swift | |
| Capture | Freemium allowance → on-device fallback, blocked → record to phone | freemium_transcription_service.dart, capture/stt_mode_resolver.dart, transcription_allowance_cache.dart | FULL | CaptureStore+Transcription.swift, ListenEvent `freemium_threshold_reached` | Flutter's plan-authoritative S17 flag (dark by default) has no native gate |
| Capture | On-device transcription (Apple speech) | sockets/on_device_apple_provider.dart | FULL | P/OmiAudio/.../OnDeviceTranscriber.swift | Flutter on-device Whisper is Android-only |
| Capture | Custom STT: OpenAI Whisper, OpenAI diarize, Deepgram, local Whisper server, custom HTTP | sockets/transcription_polling_service.dart, pure_streaming_stt.dart, composite_transcription_socket.dart | FULL | P/OmiNetwork/.../CustomSTT/*, P/OmiService/.../CustomSTT/CustomTranscriber.swift, SettingsFeature/AdvancedTranscriptionScreen.swift | Key in Keychain; Flutter `customSttConfig` migrated |
| Capture | Custom STT: Gemini live, custom live WebSocket | pure_streaming_stt.dart | MISSING | CustomSTTSettings.swift mentions Gemini only for migration | PARITY says not done |
| Capture | Primary + secondary socket (`suggested_transcript`) | sockets/composite_transcription_socket.dart | FULL | CustomTranscriber → `custom_stt=enabled` | |
| Capture | Transcription languages, multi-language detect, live translation | onboarding/primary_language, capture | PARTIAL | SettingsFeature/CaptureSettingsScreen.swift, LiveSegment.translations | Translations arrive but live UI does not show them, nor `transcriptionNotice` |
| Capture | Transcribe later (batch files) | capture, wals/local_wal_sync.dart | FULL | SyncStore+Phone.swift `omibatchphone`, Process now | |
| Capture | Listen socket reconnect | sockets/pure_socket.dart (reconnect/backoff) | FULL | CaptureStore+Interruption.swift `phoneSocketLost`/`reopenPhoneSocket`, CaptureStore+Lifecycle.swift for the Omi | The phone's socket reopens mid-recording with the same recording id; the gap goes to the phone's file and uploads at the end |
| Capture | `client_state` (foreground / transcript visible) | sockets/listen_client_state.dart | FULL | ListenSocket.swift | |
| Capture | Speaker naming during capture, speaker question reconciliation | capture/speaker_suggestions.dart | PARTIAL | Stores/LiveSpeakersStore.swift | Naming works; Flutter's suggestion reconciler not ported |
| Capture | Durable live-caption segments across crash | capture/local_segment_store.dart | MISSING | none | Low impact |
| Capture | Voice profile / guided voice introduction | onboarding/speech_profile_widget.dart, guided_voice_controller.dart | FULL | Stores/VoiceIntroStore.swift, OnboardingFeature/VoiceSteps.swift | |
| WAL | Phone-mic offline buffering → `v2/sync-local-files`, job polling, delete when done | wals/local_wal_sync.dart (2587) | FULL | SyncStore.swift, SyncStore+Phone.swift, OfflineRecordings.swift | |
| WAL | Sync page: list, play, share, delete, process now, storage meter | wals/*, pages/sync | FULL | DeviceFeature/DeviceRecordingsSection.swift, OmiComponents/PendingRecordingRow.swift | |
| WAL | Upload rate limiting: fair-use 429 pause, backend-busy backoff, account-wide upload gate | wals/sync_rate_limiter.dart, sync_upload_gate.dart, sync_rate_limit_reconciliation.dart | MISSING | none in SyncStore | Risk of hammering the backend on fair-use limits |
| WAL | Bounded upload batches (600 s stale guard) | wals/sync_upload_batch.dart | PARTIAL | SyncStore uploads per file | |
| WAL | Background transfer lease (UIApplication background task) | wals/sync_transfer_keep_alive.dart, ios/Runner/SyncTransferBackgroundLease.swift | FULL | P/OmiService/.../Stores/TransferLease.swift (refcount), App/System/BackgroundTransferLease.swift (`beginBackgroundTask`) | A read or an upload holds one grant across its batches and concurrent transfers, and hands it back when the last of them is done |
| WAL | Store audio on phone (kept copy) | local_storage_page, local_wal_sync | FULL | SyncStore `beginKeptCopy` | |
| Voice | Read answers aloud (backend TTS), reply modes, headphones-only routing | voice_playback/omi_voice_playback_service.dart, voice_output_route.dart, chat_reply_read_aloud.dart | FULL | Stores/VoicePlaybackStore.swift, SpeechPlayer.swift | |
| Voice | Progressive TTS (play while downloading) | voice_playback/progressive_tts_audio_source.dart | PARTIAL | VoicePlaybackStore splits text into short requests | Slightly later first audio |
| Notif | FCM token upload, device id hash | notifications/notification_service_fcm.dart | FULL | App/PushNotifications.swift | Same `flutter.deviceIdHash` key |
| Notif | Tap routing (`navigate_to`), cold start | services/notifications.dart | FULL | App/PushNotifications.swift, App/DeepLinkRouter.swift | |
| Notif | Task reminders (reminder/update/delete/batch delete data pushes) | notifications/action_item_notification_handler.dart | FULL | PushNotifications `TaskReminders`, OmiCore DeepLink `TaskReminderChange` | |
| Notif | `merge_completed` data push (refresh, local notification) | notifications/merge_notification_handler.dart | MISSING | none | |
| Notif | `important_conversation` data push | notifications/important_conversation_notification_handler.dart | PARTIAL | only if the push carries an APNs alert | Data-only variant shows nothing |
| Notif | Chat-answer push, suppressed while Omi speaks | notifications/chat_answer_notification_handler.dart | PARTIAL | system banner always (`willPresent` → banner) | No suppression during TTS |
| Notif | Image (rich) notifications | ios/ImageNotification/NotificationService.swift | FULL | Extensions/OmiNotificationService/NotificationService.swift | PARITY row stale |
| Notif | Proactivity v2 push, For-you feed outcomes | proactivity/proactivity_push.dart, proactivity_runtime.dart | FULL | OmiCore DeepLink `proactivity_v2`, OmiNetwork APIClient+Discover.swift | |
| Notif | Proactivity receipt outbox (durable, account-epoch fenced) | proactivity/proactivity_outbox.dart | PARTIAL | outcomes posted directly | Offline receipts lost |
| System | Capture Live Activity (Dynamic Island, lock screen, stop/pause/resume buttons) | ios/BatteryWidget/OmiCaptureLiveActivity.swift, ios/LiveActivity/*, bridges/live_activity_bridge.dart | FULL | Extensions/OmiWidgets/OmiLiveActivity.swift, Extensions/LiveActivityUI/*, Extensions/Shared/CaptureIntents.swift, App/Extras/LiveActivityController.swift | PARITY row stale |
| System | Live Activity for agent ("Omi takes over") runs | – | NATIVE-ONLY | P/OmiExtras/.../OmiActivity.swift `.agent`, LiveActivityUI/AgentViews.swift | |
| System | Battery widget (home + lock screen) | ios/BatteryWidget/BatteryWidget.swift, battery_widget_service.dart | FULL | Extensions/OmiWidgets/BatteryWidget.swift (adds accessoryInline) | Flutter's NextDeviceIntent (cycle wearables) not needed with one device |
| System | Up next / Latest conversation widgets | ios/BatteryWidget/OmiHomeWidgets.swift, home_widgets_service.dart | FULL | Extensions/OmiWidgets/HomeWidgets.swift, App/Extras/WidgetPublisher.swift | |
| System | Siri / App Intents / Spotlight | ios/Runner/SiriIntegration/* (SiriIntents.swift 741), siri_integration.dart | PARTIAL | App/System/OmiIntents.swift, OmiEntities.swift, OmiShortcuts.swift | Ask, search, open chat, remember, create/complete task, open conversation, start/stop listening, Spotlight. Missing: open memory/task/folder/list OpenIntents, "Continue in Omi" |
| System | Home-screen quick actions | quick_actions_service.dart | PARTIAL | App/System/SystemIntegration.swift | Native: Ask Omi, Add task, Start recording, My Omi. Missing: Voice mode, Mute/Unmute, dynamic Connect device |
| System | `omi://` + universal links (h.omi.me, try.omi.me) | services/notifications.dart, Info.plist | FULL | P/OmiCore/.../DeepLink.swift, App/DeepLinkRouter.swift, App/Omi.entitlements | |
| System | Phone calls (Twilio Voice, CallKit, two-channel transcript) | phone_call_service.dart, ios/Runner/PhoneCalls/* | FULL | App/PhoneCalls/*, Stores/PhoneCallStore*.swift | Needs device + Twilio keys to verify |
| System | Mic arbitration (phone mic vs. calls vs. voice input) | mic/mic_arbiter.dart, mic/native_mic_recorder_service.dart | PARTIAL | VoiceInput.swift, CaptureStore source exclusivity | No single arbiter object |
| System | Device tools for the agent (search_contacts, propose_message, request_permission) | device_tools/*, ios/Runner/DeviceToolsService.swift | FULL | App/System/DeviceToolsPerformer.swift, Stores/DeviceToolResolver.swift, OmiCore DeviceTools.swift | |
| System | Connectivity / offline hint | connectivity_service.dart | FULL | P/OmiService/.../NetworkMonitor.swift | |
| Integr | Apple Health sync | integrations/apple_health_service.dart, ios/Runner/AppleHealthService.swift | FULL | Health/AppleHealthStore.swift, HealthKitReader.swift | |
| Integr | Apple Reminders sync (incl. `apple_reminders_sync` push) | integrations/apple_reminders_*.dart, ios/Runner/AppleRemindersService.swift | FULL | Reminders/RemindersSyncStore.swift, EventKitReminders.swift | Push ignored; sync on foreground (Flutter does the same as fallback) |
| Integr | Todoist, Asana, ClickUp, Google Tasks, Gmail, Google Calendar | integrations/*_service.dart | FULL | Stores/TaskAppSettingsStore.swift, CapabilitiesStore.swift, ConversationCalendar.swift | |
| Platform | Announcements, feature screens, changelog | announcement_service.dart | FULL | Stores/AnnouncementsStore.swift, SettingsFeature/WhatsNew.swift | |
| Platform | App review prompt in onboarding setup | onboarding/setup_page.dart | FULL | OnboardingFeature/SetupStep.swift `requestReview` | |
| Platform | App review at good moments (reading surface, chat), anti-hammering budget | app_review_service.dart, app_review_policy.dart, app_review_tuning.dart | MISSING | only SetupStep | |
| Platform | Setup-rating experiment gate (PostHog flag, fail-closed) | experiments/onboarding_setup_rating_prompt.dart | PARTIAL | SetupStep always shown | Diverges: Flutter hides the page unless the flag is on |
| Platform | Conversation audio download / join / share | audio_download_service.dart, utils/audio/* | FULL | P/OmiService/.../AudioJoiner.swift, ConversationsFeature/AudioPlayerBar.swift | |
| Platform | Account cutover gate (force upgrade, migration maintenance, offline-queue quarantine) | account_cutover/* (787) | MISSING | none (`v1/account/cutover/control` never called) | Server could not stop or upgrade-gate native clients during a migration |
| Platform | Flutter → native continuity (prefs `btDevice`, `deviceIdHash`, `customSttConfig`, BLE restore id, task reminders) | – | NATIVE-ONLY | DeviceStore.swift, PushNotifications.swift:101, CustomSTTSettings.swift | |
| Platform | Product analytics (PostHog/Mixpanel events, telemetry registry) | utils/analytics/* (≈6.2k lines incl. events.g.dart 1835) | MISSING | none | docs/PLAN.md plans "Analytics-Events 1:1"; not built |
| Platform | Backend feature flags (PostHog) | env/env.dart `posthogApiKey`, experiments/*, capture/free_tier_on_device_stt_flag.dart | MISSING | none | Planned in docs/PLAN.md:59 |
| Platform | Crash reporting + boot recovery (crash-loop safe mode, boot journal) | startup/*, utils/debugging/crashlytics_manager.dart | MISSING | none | |
| Platform | Intercom support chat | utils/analytics/intercom.dart | FULL | App/System/SupportChat.swift (only with keys) | |
| Platform | Environment profiles (dev/prod API, auth emulator, physical qualification) | env/*.dart | PARTIAL | P/OmiCore/.../AppConfiguration.swift, Config/ | No physical-device qualification overrides |
| Platform | Dev controls for test harness (semantic controls, journey faults, addressability) | dev_controls/* (716) | PARTIAL | App/DebugHooks.swift, DebugLaunchOptions.swift, DebugDeviceDriver.swift | Different harness; not user-facing |
| Auth | Apple + Google sign-in (Firebase), sign out, delete account | services/auth_service.dart, onboarding/auth.dart | FULL | App/FirebaseAuthService.swift, Stores/SessionStore.swift, AuthFeature/SignInScreen.swift | Flutter's web-OAuth/custom-token path (desktop/Android) not needed on iOS; local dev token present (`signInLocalDev`) |
| Apps | Browse, search, filter by kind/category, sort (installs/rating/name) | pages/apps/explore_install_page.dart, widgets/filter_sheet.dart, category_apps_page.dart | FULL | SettingsFeature/AppsBrowserScreen.swift, Stores/AppCatalogStore.swift | Flutter sort also has lowest rating |
| Apps | Curated store home (popular, category and capability carousels) | widgets/popular_apps_section.dart, category_section.dart, capability_category_section.dart | PARTIAL | AppsBrowserScreen is one filtered list | |
| Apps | Install/enable/disable, setup steps, external-integration auth links, app home URL | app_detail/widgets/app_setup_steps.dart, app_home_web_page.dart, widgets/app_actions.dart | FULL | SettingsFeature/AppDetailScreen.swift, AppCatalogStore `signedSetupURL`, APIClient+AppStore.swift `homeURL` | |
| Apps | App detail: description (markdown), prompts, share, chat with app | app_detail/app_detail.dart, markdown_viewer.dart | FULL | AppDetailScreen.swift, OmiComponents/MarkdownBlocks.swift | |
| Apps | Permissions & triggers card, data-access consent on enable | app_detail/widgets/app_permissions_card.dart, app_actions.dart `appDataAccessMessage` | PARTIAL | SettingsFeature/PrivacyScreen.swift `accessSummary` (overview only) | Not shown on the app page or before enabling |
| Apps | Preview gallery (screenshots), capabilities card, info card | app_detail/widgets/app_preview_gallery.dart, capabilities_card.dart, info_card_widget.dart | MISSING | none | |
| Apps | Rate / review / update review, developer reply shown | app_detail/reviews_section.dart | FULL | SettingsFeature/AppReviewsSection.swift | |
| Apps | Full reviews list with star filter | app_detail/reviews_list_page.dart | PARTIAL | AppReviewsSection (inline) | |
| Apps | Paid apps: subscribe, wait for payment, cancel | app_detail.dart | FULL | AppDetailScreen `paymentSection`, AppCatalogStore `awaitPurchase`, `cancelSubscription` | |
| Apps | Disabled app state (webhook failures, last error, re-enable) | app_detail.dart `appDisabled*`, `appReEnable` | MISSING | none | |
| Apps | Chat apps / personas (use) | – (chat drawer) | FULL | AgentFeature/ChatAppPicker.swift, ChatStore+Apps.swift | |
| Apps | Create/submit/update app, AI app generator, add MCP server, app API keys, notification scopes, external triggers, payouts, own-app public/private/delete, review status | add_app.dart, add_app_provider.dart (1092), update_app.dart, add_mcp_server_page.dart, widgets/* | DROPPED | docs/PARITY.md "Left out on purpose" (building apps) | Includes persona creation |
| Onboard | Sign-in, AI consent | onboarding/auth.dart, ai_consent_widget.dart | FULL | AuthFeature/SignInScreen.swift, ConsentScreen.swift | |
| Onboard | Name, primary language (native: several ranked), where you heard of Omi | name/, primary_language/, wrapper.dart | FULL | OnboardingFeature/AboutYouSteps.swift | |
| Onboard | Pair Omi, light meanings | found_omi/, find_device/ | FULL | OnboardingFeature/OmiSteps.swift `PairStep`, `LightsStep` | |
| Onboard | Power-cycle step (hold to turn off, turn on, reconnect) | interactive_device_onboarding/steps/power_cycle_step.dart | MISSING | none | Low impact |
| Onboard | Single press (ask), double press config, spoken-reply preview, transcription demo, all-set summary | interactive_device_onboarding/steps/* | FULL | OnboardingFeature/OmiButtonSteps.swift, VoiceReplyStep.swift, OmiButtonTutorialScreen.swift | |
| Onboard | Guided voice intro answers saved as memories | guided_voice_controller.dart, guided_voice_io.dart | FULL | VoiceIntroStore.swift:290 `createMemory` | |
| Onboard | Spoken goal prompt saved as a goal | guided_voice_controller.dart `saveGoal`, goal_text_cleanup.dart | MISSING | VoiceIntroStore has no goal | |
| Onboard | Permissions (notifications, mic, location) | permissions/* | FULL | OmiSteps.swift `PermissionsStep` | |
| Onboard | Apple Watch permission | apple_watch_permission_page.dart | FULL | OnboardingFeature/WatchStep.swift | |
| Onboard | Knowledge-graph step | knowledge_graph_step.dart | DROPPED | moved to Settings › Memory (PARITY) | |
| Onboard | Setup page + rating, completion + Siri hint | setup_page.dart, complete_screen.dart | FULL | SetupStep.swift, App/System/SiriTipSheet.swift | |
| Onboard | Intro tour with demos (listen, memory, voices, for you, hand-over, lock screen) | – | NATIVE-ONLY | OnboardingFeature/IntroSteps.swift, IntroDemos.swift | |

## Counts

FULL 67 · PARTIAL 18 · MISSING 18 · DROPPED 6 · NATIVE-ONLY 3 · n/a 1 (113 rows).

## Biggest gaps (ranked by user impact)

1. **Legacy offline-storage protocols** (SD-card < 3.0.20 and multi-file LittleFS): an Omi on older firmware syncs
   nothing it recorded offline. `wals/sdcard_wal_sync.dart`, `wals/storage_sync.dart`. Mitigation: force the
   firmware update first, or port both (~1.8k Dart lines).
2. **Upload rate limiting** (fair-use 429 pause, backend-busy backoff, serialized upload gate) missing in SyncStore:
   the app keeps sending while the backend is asking it to slow down.
3. **Account cutover / force-upgrade gate** missing: the backend cannot fence or upgrade-gate native clients during an
   account migration (`v1/account/cutover/control`).
4. **No analytics, feature flags or crash reporting**: no PostHog/Mixpanel events, no remote flags, no Crashlytics or
   boot-loop recovery. Product cannot measure or remotely switch native behavior; crashes are invisible.
5. **Legacy Nordic DFU** missing: old DevKit/Friend units cannot be updated from native.
6. **Data-only pushes** `merge_completed` and `important_conversation` are dropped; chat-answer pushes are not
   suppressed while Omi speaks.
7. **App store polish**: no permissions/data-access card or consent on enable, no screenshots gallery, no
    disabled-app/re-enable state, no full reviews list. Plus smaller ones: quick actions (voice mode, mute),
    Siri open-memory/task/folder intents, review prompts after good moments, power-cycle onboarding step,
    spoken-goal capture, live translation display, Gemini/custom live STT.

## Why Flutter is bigger here

Rough sizes for this slice: Flutter Dart ≈ 62.3k lines (services + apps + onboarding + startup/core/env) + 12.8k
utils + ≈ 24k Swift/ObjC in `app/ios`; native equivalent is ≈ 11k lines (OmiDevice 882, OmiAudio 542, OmiExtras 441,
App/ 4.3k, Extensions 1.6k, Watch 465, plus capture/sync/device/onboarding/app-store stores and screens ≈ 6-7k).

1. **Many device types (≈ 7.3k lines)**: other wearables in Dart 5,623 (`limitless_connection.dart` alone 2,134,
   `omiglass_connection.dart` 677, `flash_page_wal_sync.dart` 838, Ray-Ban transport/discoverer/bridge ≈ 700) plus
   1,701 Swift (`Runner/Limitless/*`, `Runner/RayBanMeta/*`). Native: 0 (dropped).
2. **Three Omi storage protocols instead of one**: legacy SD 1,035 + multi-file 775 alongside ring/custody 2,121.
   Native ring-only: `OmiStorage.swift` 219 + `SyncStore` ≈ 610.
3. **Capture orchestration built for cross-platform and hardening**: `capture_controller.dart` 4,084 +
   `capture_coordinator.dart` 2,855 = 6,939, plus 2,185 for wedge monitor, metrics, lifecycle telemetry, ingress
   health, policy, lifetime, seams, scenarios. Native `CaptureStore` + 3 extensions ≈ 1,100.
4. **Platform channels and generated glue**: Pigeon `.g.swift` 3,326 (PigeonCommunicator 1,955, SiriPigeon 1,036,
   PhoneMicPigeon 335) plus the Dart side; `analytics/registry/events.g.dart` 1,835; `GeneratedPluginRegistrant` 341.
   Native calls frameworks directly.
5. **A second, Swift BLE + phone-mic stack under Flutter**: `Runner/Ble/*` 2,551 and `Runner/PhoneMic/*` 1,951 exist
   because Flutter's plugins were not good enough for background capture; then Dart wraps them again
   (`native_ble_transport.dart` 482, `native_mic_recorder_service.dart` 324). Native: `OmiDeviceManager.swift` 316,
   `PhoneMicCapture.swift` 117.
6. **Telemetry, analytics and debug tooling (≈ 10k)**: `utils/analytics/*` ≈ 6.2k (`analytics_manager.dart` 2,855),
   `SiriDebugProbe.swift` 1,158 + `SiriSnapshotStore.swift` 1,090, `dev_controls/*` 716, `startup/*` 262 boot
   recovery, ≈ 1,070 Logger/debug calls and 70 `@visibleForTesting` seams in `services/`. Native has none of the
   analytics and only small debug hooks (≈ 280 lines in App/Debug*).
7. **Server-migration and fencing machinery**: `account_cutover/*` 787, `sync_upload_gate` / rate limiter /
   reconciler / keep-alive / batch / evidence runs 1,544, `proactivity_outbox` 186. Mostly missing natively.
8. **App creation surface**: create/update/MCP/AI generator/API keys/payouts forms ≈ 3,700 lines
   (`add_app_provider.dart` 1,092, `add_app.dart` 428, `app_form_fields.dart` 409). Dropped natively.
9. **Android and multi-platform branches**: 64 Android references in the slice, `Platform.isIOS` forks
   (e.g. `transcription_service.dart:614` Whisper vs. Apple), Android foreground-service code paths in keep-alive.
10. **Verbose widget trees and animations**: onboarding 7,158 lines vs native ≈ 3,100; e.g.
    `double_tap_demo_animation.dart` 322, `found_devices.dart` 475, `speech_profile_widget.dart` 620 vs native
    `VoiceSteps.swift` 304. Vendored code: `minimp3.h` 1,865 for TTS decoding (native uses AVAudioPlayer).
