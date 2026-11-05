# Parity: Flutter → native

The Flutter app (`omi-fresh/app/lib/…`, iOS extras in `app/ios/…`) is the reference: every capability it
has is either here, planned, or listed under "Left out on purpose" with a decision. The native app keeps
the UI simpler; it does not drop capabilities silently.

Status: ✅ done · 🟡 partial · ❌ missing. Effort S/M/L. Native paths are under
`Packages/OmiFeatures/Sources/` unless they start with `App/` or name a store. Audit of 2026-10-07
(master `42d23aa`): 233 rows, ✅ 76 · 🟡 26 · ❌ 131.

## Onboarding/Auth
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Apple/Google sign-in | onboarding/auth.dart | ✅ AuthFeature/SignInScreen | |
| AI consent gate | onboarding/ai_consent_widget | ✅ AuthFeature/ConsentScreen | |
| Name, language (native: several, ranked), where you heard of Omi | onboarding/name, primary_language, wrapper | ✅ OnboardingFeature/AboutYouSteps | |
| Choose device type, find other devices | device_selection, find_device | 🟡 Omi only | L |
| Pair Omi, light tutorial, transcription demo, voice profile | found_omi, steps/*, speech_profile_widget | ✅ OmiSteps, VoiceSteps | |
| Single press = ask a question | steps/single_press_step | ✅ OnboardingFeature/OmiButtonSteps `AskOmiStep` (Omi path only): a real question through `ButtonTutorialStore` → AskOmiStore, answer shown; also Settings › My Omi › Help with your Omi › Learn the button again | |
| Double-press action setup | steps/double_press_config_step | ✅ OmiButtonSteps `DoublePressStep` (Omi path only): same setting as Settings › My Omi › Controls (`DeviceStore.doubleTapAction`, default End conversation); practice presses only count | |
| Spoken-reply preview | steps/voice_reply_step | ✅ OnboardingFeature/VoiceReplyStep: last answer (or a sample) in the chosen voice, Off / With headphones / Always (first run starts Off, as Flutter), live output line | |
| Permissions | onboarding/permissions | ✅ OnboardingFeature/PermissionsStep: notifications, microphone, location (When In Use; also Settings › Privacy & data). Background activity is Android-only in Flutter | |
| Apple Watch permission | apple_watch_permission_page | ✅ OnboardingFeature/WatchStep (only with a paired watch, `WatchLink.isWatchPaired`): watch app installed, microphone asked on the watch (`WatchStore.requestMicrophone`), help | |
| "What I know about you" (knowledge graph) | knowledge_graph_step | ✅ Settings › Memory (SettingsFeature/KnowledgeSummaryScreen), not an onboarding step | |
| Setup screen + rating prompt | setup_page | ✅ SetupStep | |
| Completion screen with Siri hint | complete_screen | ✅ setup step ends in the app; one-time "Ask Omi with Siri" row in Home's For you card (App/System/SiriTipSheet) | |
| Announcements, feature screens, changelog | announcements/* | ✅ SettingsFeature/WhatsNew (sheet after an update, `lastKnownAppVersion`; Help › What's new), AnnouncementsStore | |
| Replay introduction | – | ✅ Settings › Help (SettingsFeature/HelpScreen) | |

## Home
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Device pill with battery, Ask Omi bar + voice, Home/Chat/Memories (tasks on Home: Needs you, All tasks), live card, daily recaps | home/* | ✅ | |
| "Record with…" sheet (phone mic, phone call, one source at a time) | battery_info_widget | ✅ long press on record: App/RecordWithSheet (iPhone, Omi, Apple Watch); phone calls stay in Settings › Phone calls | |
| "For you" cards with helpful / not helpful / stop these | home_for_you | ✅ TodayFeature/ForYouCard: one card with Omi's runs, due tasks, recommendations, speaker prompts and nudges (HomeAttention order); feedback in the row menu | |
| Goals widget | goals_widget | ✅ TodayFeature/GoalsCard (only when goals exist, at most 2; title opens all goals) | |
| Header sync button | header_sync_button | 🟡 dot on the device pill | S |
| Capture recovery banner | capture_recovery_banner | ✅ TodayFeature/CaptureRecoveryBanner: app closed while recording, connection dropped (audio kept on the phone, Upload now); no zero-byte / rapid-reconnect heuristics | |
| "Who is this?" speaker prompt card | speaker_tag_prompt_card | ✅ TodayFeature/SpeakerPromptCard, VoicesStore | |
| Tasks: export, show completed | home/page | ✅ All tasks (Home) › … › Export all open; Done section | |

## Conversations list
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| By day, paging, pull to refresh | conversations_page | ✅ | |
| Processing / failed-summary retry | conversation_list_item | ✅ row pill + Retry, context menu (reprocess) | |
| Star + starred filter | conversation_actions | ✅ swipe right / context menu; Home filter menu | |
| Folders: create, edit, delete, move, tabs | create_folder_sheet, folder_options_sheet, move_to_folder_sheet | ✅ FolderSheets; tabs = Home filter menu | |
| Multi-select, bulk delete/move, merge | merge_action_bar, merge_confirmation_dialog | ✅ TodayFeature/SelectionBar | |
| One-day page, map view | day_conversations_page, conversation_map_page | ✅ map: TodayFeature/ConversationMapScreen (Home filter menu › Conversation Map; places within 100 m, `ConversationPlace`); one-day page: Home filter menu › Filter by date (TodayFeature/ConversationListExtras `DayConversationsScreen`, `DayConversationsStore`: previous/next day, calendar, show more) | |
| Show short / discarded conversations | conversation_display_settings | ✅ Home filter menu › Conversation Display (TodayFeature/ConversationListExtras `DisplayOptionsMenu`; `ConversationsStore+Display`, Flutter keys `showDiscardedMemories`, `showShortConversations`, `v2/shortConversationThreshold`); one row per capture group | |
| Swipe to delete | conversation_list_item | ✅ swipe left, 5 s undo toast | |
| Locked items / upgrade | conversation_list_item | ✅ frosted row with "Upgrade to Unlimited" (TodayFeature/ConversationListExtras `LockedRowCover`) opens Account (`\.openUpgrade`) | |

## Conversation detail
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Summary (structured markdown, other apps' results) | summary_tab | ✅ ConversationSummaryView (summary, key points, events, apps) | |
| Action items, transcript with speakers, rename, delete, Omi takes over | summary_tab, transcript_tab | ✅ ConversationDetailScreen | |
| Share as link, visibility private/shared | share.dart, conversation_detail_header | ✅ link (private again if not shared), text, Make private | |
| Copy transcript / summary / ID | page | ✅ Copy ID with Developer › Conversation developer tools | |
| Reprocess | page | ✅ | |
| Summary template: switch app, default, create | summarized_apps_sheet, create_template_bottom_sheet | ✅ … › Summary Template (ConversationsFeature/SummaryTemplateSheet, `SummaryTemplatesStore`): suggested + installed apps, tap = reprocess with that app, swipe = default, Create Custom Template; "Summarized by <app>" under the summary. "All templates" (app store by capability) not linked | |
| Star, move to folder | page | ✅ | |
| Calendar event: link, open, share with attendees | calendar_event_sheets | ✅ … › Link Event (Google Calendar; connect prompt when not connected), linked event card + sheet: open in Google Calendar, share with attendees (mail), unlink (ConversationsFeature/ConversationCalendar); found events add to the iPhone calendar (system editor, `created` saved) | |
| Search inside the conversation | detail_search_bar | 🟡 transcript only (highlight, previous/next) | S |
| Audio playback / download / share | audio_download_progress_sheet | ✅ AudioPlayerBar; several parts are joined into one file (OmiService/AudioJoiner: MP3 concatenated, WAV re-headed) that plays and shares; precache on open | |
| Capture recordings: view, separate | capture_recordings | ✅ … › Recordings (n) (ConversationsFeature/CaptureRecordingsSheet): open another device's recording, Separate…; Home shows one row per group | |
| Name / tag speakers, earlier voice matches, update summary with names | name_speaker_sheet, earlier_voice_matches_sheet, speaker_summary_action | ✅ NameSpeakerSheet, VoiceMatchesSheet, TranscriptSpeakersStore | |
| Edit a transcript segment | edit_segment_sheet | ✅ long press | |
| Helpful? feedback | feedback_sheet | ✅ ConversationsFeature/SummaryFeedbackRow, `SummaryFeedbackStore` (Flutter policy: 25 % sample, once a week, once per conversation; `v1/mobile/feedback`) | |
| Share by SMS to contacts | share_to_contacts_sheet | ✅ Share › Share via SMS (ConversationsFeature/ShareBySMS): system contact picker, then the Messages composer with the link; nothing is sent by the app | |
| Participants, screenshots/photos, location map, processing strip | conversation_detail_header, screenshots, maps_util, activity_strip | ✅ location map + area/city: OmiComponents/ConversationPlaceCard (opens Maps); location captured at recording start (`LocationStore` → `X-Omi-Conversation-Geolocation`); participants chip, photos (transcript tab), "What was on screen" screenshots, processing strip with polling: ConversationsFeature/ConversationMedia | |
| Ask Omi about this conversation | chat scope | ✅ menu → chat with context | |
| Test prompt (developer) | test_prompts | ✅ … › Test Prompt when Developer › conversation developer tools is on (ConversationsFeature/CaptureRecordingsSheet `TestPromptSheet`) | |

## Tasks
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Buckets, create/edit/delete with due date, complete, search, reminders | action_items_page, action_item_form_sheet | ✅ | |
| Clear completed | action_items_page | ✅ All tasks › … (with Undo) | |
| Undo delete, multi-select bulk delete | task_delete_undo, task_selection_action_bar | ✅ 5 s undo toast; TaskSelectionBar (done, export, share, delete) | |
| Subtasks (indent/outdent) | action_items_page | ✅ context menu Indent / Outdent (`indent_level`), nested rows; no drag | |
| Export to Todoist / Asana / ClickUp / Google Tasks | task_integrations_page | ✅ context menu / selection, to any connected app or Reminders | |
| Share task link / accept shared tasks | accept_shared_tasks_sheet | ✅ link from menu or edit sheet; `omi://tasks/<token>` and `https://h.omi.me/tasks/<token>` open SharedTasksSheet | |
| One-day tasks page | day_tasks_page | ✅ DayTasksScreen from the Today header (due + added, previous / next day) | |
| Goals: create, edit, progress | goals_page, goal_form_sheet | ✅ GoalsScreen (All tasks › …), GoalFormSheet, − / +, delete with Undo | |
| Apple Reminders sync | ios/Runner/AppleRemindersService | ✅ RemindersSyncStore + EventKit, "Omi" list, All tasks › … › Sync with Reminders; also on / off in Settings › Apps & integrations | |

## Memories
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| List, categories, search, add/edit/delete, source conversation, all pages | memories/* | ✅ | |
| Filters interesting/manual/system | memory_management_sheet | ✅ chips About you / Insights / Manual, then other categories | |
| Undo delete, delete all | memory_delete_undo, memory_management_sheet | ✅ 5 s undo toast; Delete all in Settings › Memory (confirmed) | |
| Visibility per memory / all | memory_management_sheet | ✅ context menu + edit sheet; header menu Make all private/public with counts | |
| Pin as baseline, review right/wrong, source device | memory_edit_sheet, memory_item | ✅ MemoryCard: pin, "Is this right?" on new memories (wrong discards), device line | |
| Memory graph + share | memory_graph_page | ✅ MemoryGraphScreen (header menu): native 2D force layout, tap highlights neighbours, share as image | |

## Chat/Agent
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Streamed answers, steps, history, earlier messages, starters, dictation, stop/retry/copy | chat/* | ✅ AgentFeature | |
| Referenced conversations tappable | ai_message | ✅ MessageBubble → MainTabView | |
| Specific errors (quota, offline, timeout) | ai_message | ✅ ChatStore+Extras, Upgrade → Account | |
| Attachments: photo, camera, file | files_handler_widget | ✅ ChatAttachments (v2/files, max 4) | |
| Clear chat | chat/page | ✅ ChatMenu (main session only) | |
| Chat apps / personas | chat_apps_drawer | ✅ AgentFeature/ChatAppPicker, ChatStore+Apps: one backend session per app (`app_id`), main chat and agent runs untouched | |
| Thumbs up/down, share message, follow-up chips, charts | message_action_bar, chat_followup_chip, chart_message_widget | ✅ AnswerMenu (long press on an answer), ChartCard | |
| Read replies aloud (TTS) | services/voice_playback | ✅ VoicePlaybackStore (v2/tts, reply mode, speaker button, preview) | |
| Offline hint | chat_chrome | ✅ NetworkMonitor | |

## Search
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Server search; tasks and memories | search/global_search | ✅ SearchScreen | |
| Filters, recent searches | global_search | ✅ starred, person, date range, recaps; 6 recent searches (`globalSearchRecentQueries`); places stays with the map row | |
| Settings search | settings_search_index | ✅ SettingsFeature/SettingsSearch: field on top, opens the screen that holds the setting | |

## People/Speakers
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| List / add / rename / delete, record your voice again | settings/people, voice_profile | ✅ PeopleScreen | |
| Search people, clean up, ignored voices, ask-to-tag toggles | people_* | ✅ PeopleScreen, PeopleCleanUpScreen, IgnoredVoicesScreen | |
| Person detail: samples, talk time, conversations, pin | person_detail_page | ✅ PersonDetailScreen; a conversation row closes Settings and opens it (`onOpenConversation` from the shell) | |

## Apps/Integrations
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Installed apps, browse/search, enable/disable; calendar, mail, task apps | apps/*, integrations_page | ✅ Settings › Apps & integrations (CapabilitiesScreen: connected / add, your apps); store: AppsBrowserScreen (kind chips, search, category and sort, loading / empty / error with Try again). Local demo catalog: Tools/dev/seed_demo_apps.py | |
| App detail, reviews, categories, paid apps | app_detail/* | ✅ SettingsFeature/AppDetailScreen, AppReviewsSection, AppCatalogStore (setup steps, rate/review, chat with app, share, subscribe/cancel; browse by kind, category, sort) | |
| Create / submit / manage own apps, AI app generator, MCP server, payouts | add_app, ai_app_generator_page, add_mcp_server_page, payments/* | ❌ | L |
| Per-integration settings | todoist/asana/clickup/google_tasks_settings_page | ✅ SettingsFeature/TaskAppSettingsScreen: default app, Asana workspace/project, ClickUp team/space/list, disconnect | |
| Apple Health | apple_health_detail_page | ✅ Settings › Apps & integrations › Apple Health (`AppleHealthStore`, `HealthKitReader`): 7-day summary to `PUT v1/integrations/apple-health/sync`, again on return to the app (hourly at most) | |

## Device (Omi)
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Pair/forget, firmware update, reconnect, low battery, offline sync | device_settings, firmware_update, wals | ✅ | |
| Unpair, charging state, full device info | device_settings, device_page_header, device_info_groups | ✅ DeviceScreen (charging bolt, serial, hardware, manufacturer); Unpair is Limitless-only in Flutter, Omi has Forget | |
| Double-tap action choice (end / star / mute) | device_control_sheets | ✅ DeviceControlsSection, `ButtonAction.route`, button actions toggle | |
| Single press = ask (push-to-talk) | single_press_step | ✅ AskOmiStore → `v2/voice-messages`, answer in chat, read aloud by VoicePlaybackStore as Spoken replies allows (a new question cuts it off); notification only when not spoken | |
| Mute, LED brightness, mic gain, find device | device_control_sheets | ✅ DeviceControlsSection (one-line rows, explanations in the footer), feature-flag gated | |
| Diagnostics, charging help, tutorial links, Get Omi | device_settings, device_diagnostics | ✅ one row "Help with your Omi" (DeviceFeature/OmiHelpScreen): Learn the button again (OmiButtonTutorialScreen), Connection health (DeviceDiagnosticsScreen: now, 7-day verdict, signal + battery charts, drops; Share / Send to support → `v1/mobile/device-diagnostics`, `DeviceDiagnosticsLog`), charging help; Get Omi on the device screen. No firmware/BLE logs (Flutter's native layer) | |
| Sync page: recordings, process now, delete, play, share; auto-remove; storage meter | sync_page, auto_sync_page, device_storage_card | 🟡 DeviceRecordingsSection + OmiComponents/PendingRecordingRow (Opus decoded to WAV on the phone), the Omi's storage meter (DeviceStorageCard). A file goes as soon as the backend's job completes; the "remove synced copies after N days" switch (`autoRemoveSyncedCopies`, default 30) has no counterpart, and neither have cancel sync, delete-all or the synced-conversations result page | |
| Firmware rollback, custom firmware zip | firmware_update, developer_firmware_flash_page | ❌ waits for the product owner's approval (never flashes) | S |

## Capture/Transcription
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Phone + Omi capture, stop, language, vocabulary, on-device transcription | capture/*, settings/* | ✅ | |
| Full live-transcript screen | conversation_capturing/page | ✅ LiveBar → TodayFeature/LiveTranscriptSheet | |
| Pause / resume, identify speaker during capture | conversation_capturing | ✅ pause/resume (`CaptureStore.pause`); tap a speaker in the live transcript to name it (`LiveSpeakersStore`, shared `SpeakerNamePicker`) | |
| Phone-mic offline buffering | wals/local_wal_sync | ✅ CaptureStore+Recovery, SyncStore+Phone: a dropped (or unavailable) socket keeps recording into a `phonemic` PCM16 WAL file, uploaded to `v2/sync-local-files` when it stops. The socket comes back mid-recording with the same recording id (`CaptureStore+Interruption.phoneSocketLost`): the audio of the gap goes to the file, the rest of the conversation streams live again | |
| Microphone taken away, stuck capture | capture/capture_wedge_monitor, capture_ingress_health | ✅ CaptureStore+Interruption: a call, Siri or a route change pauses capture and the app asks for the microphone back until it has it; a probe every few seconds restarts a capture whose engine died without saying so. Home says why it is quiet (`CaptureRecoveryBanner`, `CaptureNotice`) | |
| Conversation timeout, background mode | conversation_timeout_dialog, settings_groups | ✅ timeout in Settings › Listening (End after silence); background mode is Android-only in Flutter | |
| Transcribe later, Whisper model, custom STT provider, STT logs, translation, freemium fallback | transcription/* | ✅ Transcribe later (`omibatchphone` files, Process now), Detect languages = Automatic translation (`single_language_mode`; live `translating` events land on `LiveSegment.translations`), server model Omi / Parakeet (`stt_service`), transcription log (custom STT logs there too, never the key). Custom STT: Settings › Listening › Advanced › Advanced transcription (OpenAI Whisper, OpenAI diarize, Deepgram live, Local Whisper, custom HTTP endpoint; key in the Keychain, Flutter's `customSttConfig` migrated) → `custom_stt=enabled` + `suggested_transcript` (`CustomTranscriber`). Whisper model: Flutter iOS uses Apple speech, no download; native's on-device switch is that. Freemium: `transcription_allowance` / `freemium_threshold_reached` → the iPhone transcribes (at start or mid-recording), `blocked` records to the phone (`CaptureStore+Transcription.swift`). Not: Gemini live and custom live WebSocket providers; the live-transcript UI does not show translations or `transcriptionNotice` yet | |

## Settings, Account, Notifications
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Daily summary, appearance, app language, cloud recordings, permissions, delete account, help | settings/* | ✅ | |
| Plan, quota, upgrade, portal, sign out | usage_page, plans_sheet | ✅ Account › Plan & usage (SettingsFeature/PlanUsageScreen + PlanPicker, `PlanStore`, `PlanCatalog`): plan name with renews / ends on, this month's meters against the limits (listening minutes, chat questions or AI spend, words and insights where limited; amber from 80 %, red at the limit; reset date); the plans from `GET v1/payments/available-plans` (fallback: the subscription's `available_plans`) grouped per plan, Monthly / Yearly with the saving computed from the prices, feature lines, promo code; free or cancelled → `POST v1/payments/checkout-session` (Stripe page in SFSafariViewController, or reactivated in place), running plan → confirm, `POST v1/payments/upgrade-subscription`; desktop plans (Operator, Architect) manage-only; the plan is read again on return ("You're on Plus now"); payment method and invoices → customer portal; refusals in the backend's words, an unreachable service says nothing was charged. Every Upgrade button (locked conversations, chat quota) opens this screen; sign out in Account. Not: training-data opt-in and "switch to on-device" downgrade from Flutter's sheet | |
| Push token, tap routing, task reminders, agent finished, low battery | notifications/* | ✅ App/PushNotifications, DeepLinkRouter | |
| Notification frequency (6 levels), assistant voice preview | notifications_settings_page, voice_settings_page | ✅ Settings › Assistant: all six levels with descriptions, daily recap and time, voice list with previews; Notifications shows the iOS permission and links there | |
| Profile: change name, copy user ID | profile, change_name_widget | ✅ name in Account (local name + Firebase display name, like Flutter); user ID (copy) in Developer | |
| Store audio on phone, data access overview, export all data | local_storage_page, data_privacy_page, data_export | ✅ PrivacyScreen: export (`v1/users/export` → share), app access; Store audio on phone (Flutter's `unlimitedLocalStorageEnabled`) keeps a copy of every live phone-mic and Omi recording on the phone (`SyncStore.beginKeptCopy`, never uploaded; play/share/delete in Recordings on phone) | |
| Import data / history | import_history_page | ✅ Settings › Memory › Import history (ImportScreen): Limitless zip → `v1/import/limitless`, jobs with progress, cancel, delete (delete-imported is a backend stub, not offered) | |
| Developer settings (webhooks, API/MCP keys, logs, experimental) | developer/* | ✅ SettingsFeature/DeveloperScreen behind Help › Developer mode: user ID, 4 webhooks (audio interval), API keys (read-only / full), MCP keys + config, debug log file, VAD gate, conversation tools. Payouts and custom firmware are separate rows | |
| Intercom chat, what's new, referral | feedback_sheet, changelog_sheet, referral_page | ✅ what's new (Help), referral (Account › Invite friends: link, share, copy, how it works, program page); Intercom (SPM `intercom-ios-sp` 19.8.4, `App/System/SupportChat.swift`) in Help when `OMI_INTERCOM_APP_ID` + `OMI_INTERCOM_IOS_API_KEY` are set, else help center + feedback only | |
| Wrapped | wrapped_2025_page | dropped by owner decision 2026-10-07 | |
| Phone numbers: delete | phone_call_settings_page | ✅ SettingsFeature/PhoneCallsScreen (swipe or hold, confirm), PhoneCallStore | |
| Cancel subscription in-app, usage stats, fair use | cancel_subscription_sheet, usage_page, fair_use_page | ✅ Account › Plan & usage (PlanUsageScreen): what Omi heard (4 periods, chart, share), fair-use meters, cancel → CancelSubscriptionSheet (`DELETE v1/payments/subscription`) | |
| Image notifications | ios/ImageNotification | ✅ OmiNotificationService/NotificationService.swift (a push with a picture attaches it before it is shown) | |

## iOS system integration
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| `omi://` links, share conversation, review prompt, background audio + Bluetooth | Info.plist, share_sheet | ✅ | |
| Capture Live Activity, Dynamic Island, lock screen | ios/BatteryWidget/OmiCaptureLiveActivity, ios/LiveActivity/* | ✅ OmiWidgets/OmiLiveActivity.swift + Extensions/LiveActivityUI, drawn from the app by App/Extras/LiveActivityController.swift | |
| Battery widget, Up next / Latest widgets | ios/BatteryWidget/* | ✅ OmiWidgets/BatteryWidget.swift + HomeWidgets.swift, refreshed through OmiExtras/WidgetReload | |
| Watch app (record, battery) | ios/omiWatchApp | ✅ Watch/ (OmiWatch target): record from the wrist (WatchRecorder, WatchMicrophone), the Omi's battery, recordings start in the app | |
| Siri / Shortcuts (ask, remember, tasks, search, open, start/stop listening), Spotlight | ios/Runner/SiriIntegration | ✅ App Intents + App Shortcuts (en/de), entities for conversations/tasks/memories/folders, Spotlight index (App/System) | |
| Home-screen quick actions | services/quick_actions_service | ✅ Ask Omi, Add task, Start recording, My Omi (no voice mode / mute) | |
| Universal links (h.omi.me) | Info.plist | ✅ conversations, recaps, /unlimited, /apps/<id> (app page sheet, "not available" when unknown), /tasks/<token> (shared tasks); /wrapped only opens the app (Wrapped is being retired) | |
| Background fetch/processing, location, VoIP, CallKit calls | Info.plist, ios/Runner/PhoneCalls | ✅ VoIP background mode + CallKit outgoing calls (App/PhoneCalls, no PushKit: Flutter has none); `<bundle id>.refresh` / `.processing` BGTasks (`App/System/BackgroundTasks.swift`, `BackgroundWork`: upload recordings, refresh lists); a transfer that is still running when the app is put down holds a background task of its own (`TransferLease`, `App/System/BackgroundTransferLease.swift`: reading the Omi, uploading files); `location` background mode with When In Use only (`CoreLocationProvider`) | |

## Other platforms/devices
| Feature | Flutter | Native | Eff |
|---|---|---|---|
| Phone calls (dial, contacts, active call transcript, number setup) | pages/phone_calls/*, phone_call_provider, ios/Runner/PhoneCalls | ✅ Settings › Phone calls: number setup + code, keypad + Contacts picker, active call (live two-channel transcript, translations, mute, keypad tones, speaker, audio route, minimize banner), past calls; Twilio Voice SPM + CallKit (App/PhoneCalls), PhoneCallStore. Needs a device + Twilio keys to verify | |
| Limitless, Ray-Ban Meta, OmiGlass, Apple Watch source, Bee/Fieldy/Plaud/Friend | connectors/* | 🟡 Apple Watch: onboarding WatchStep + Record with… sheet; other wearables left out (Decisions) | L |

## Decisions (2026-10-07, with the product owner)
In scope, beyond what the rows above already plan: developer settings, phone calls, goals, map and
places, Apple Health and Reminders, referral / what's new (Wrapped was later dropped, owner decision
2026-10-07).

Left out on purpose:
- Other wearables (Limitless, Ray-Ban Meta, OmiGlass, Bee, Plaud, Fieldy, Friend, custom): each is a
  separate Bluetooth protocol that cannot be tested without the hardware; the native app is for Omi.
- Building apps (create/submit/manage own apps, AI app generator, MCP server setup, creator payouts):
  a developer surface, not part of using Omi. Installing and using apps stays.
