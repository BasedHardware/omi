# Screen map — design → Flutter file on `main`

Paths are relative to `app/lib/`. Renders: `renders/dark/<Screen>.png`, `renders/light/<Screen>.png` (393×852 pt at 2×).
Behaviour for every control: `spec/screens/*.md` (search the screen name). Wires (`renders/wires/`) show the
multi-device direction (Rev 3); the dark/light renders are the visual target.

## Order to build (each row is one small PR)

| # | Design screen | Replaces / restyles on main | Notes |
|---|---|---|---|
| 0 | Tokens + components | `ui/omi_tokens.dart`, `ui/omi_theme.dart`, `ui/components/*` | Apply `flutter/omi_tokens_v2.dart` values to the existing names. Add `OmiRingLogo`. No page edits yet. Whole app restyles. |
| 1 | Tab bar + Ask | `widgets/bottom_nav_bar.dart`, `pages/home/home_navigation.dart` | Floating capsule + round Ask button with `OmiRingLogo(mode: breathe)`. Icons: `icons/glyphs/{house,bubbles,checklist,grid}[-fill].svg` via `flutter_svg`; filled = selected. |
| 2 | `Main` (Home) | `pages/home/home_content.dart`, `pages/conversations/widgets/live_capture_card.dart` | Device pill leading, Search + Account trailing. Live card: Pause/Resume + End (`flutter/live_capture_controls.dart`). Keep `pauseCapture/resumeCapture/finishCapture`. |
| 3 | `Live` | `pages/conversation_capturing/page.dart` | Source + timer header, transcript, Pause + End. |
| 4 | `Conversations`, `ContextMenu`, `Offline` | `pages/conversations/conversations_page.dart`, `pages/conversations/widgets/*` | Day sections, folder chips, long-press menu via existing row-menu primitive. |
| 5 | `Conversation`, `Speaker`, `ShareCard` | `pages/conversation_detail/page.dart`, `widgets.dart`, `share.dart` | One summary block (never duplicated), Summary / Transcript / Tasks segmented, no map when place unknown. |
| 6 | `Processing` | `pages/processing_conversations/page.dart` | Real states only (processing / discarded / failed). |
| 7 | `Tasks`, `TaskEdit` | `pages/action_items/action_items_page.dart` | Buckets, duplicate suggestion (user-driven), quick add above tab bar. |
| 8 | `Chat`, `VoiceAsk` | `pages/chat/page.dart` | `OmiRingLogo(mode: chase)` while thinking. |
| 9 | `Memories`, `MemoryDetail`, `Graph` | `pages/memories/page.dart` | Tier chips; graph from `GET v1/knowledge-graph` only. |
| 10 | `Recap` | `pages/conversations/daily_recaps_page.dart`, `pages/settings/daily_summary_detail_page.dart` | Journal layout. |
| 11 | `Apps`, `AppDetail`, `Integrations` | `pages/apps/page.dart`, `pages/apps/app_detail/*`, `pages/settings/integrations_page.dart` | Enable vs Set Up capsules; guide instead of “App setup is not completed” error. |
| 12 | `Settings` + sub-pages | `pages/settings/settings_drawer.dart`, `settings_groups.dart` and the pages below | Keep main's Account + groups structure. |
| 12a | `Device`, `Firmware` | `pages/settings/device_settings.dart`, `pages/home/firmware_update.dart` | Sliders only when the device reports the feature. |
| 12b | `Plan`, `Upgrade` | `pages/settings/usage_page.dart`, `pages/settings/widgets/plans_sheet.dart` | Stripe checkout (existing), Plus + Unlimited only. |
| 12c | `Privacy`, `DeleteAccount` | `pages/settings/data_privacy_page.dart`, `pages/settings/delete_account.dart` | |
| 12d | `Notifications`, `Transcription`, `Language`, `People`, `Appearance` | `pages/settings/notifications_settings_page.dart`, `transcription_settings_page.dart`, `language_settings_page.dart`, `people.dart` | Appearance (theme/icon) is new; phase 2 with light theme. |
| 13 | `Sync` | `pages/conversations/sync_page.dart`, `auto_sync_page.dart`, `local_storage_page.dart` | Per-recording state labels already exist (`capture_state_labels.dart`). |
| 14 | `Pairing`, `Discover` | `pages/capture/connect.dart`, `pages/onboarding/find_device/*`, `pages/onboarding/device_selection.dart` | “Other ways to listen”: watch / glasses / iPhone icons. |
| 15 | Onboarding: `Welcome`, `SignIn`, `Consent`, `Name`, `Language`, `Source`, `Permissions`, `Voice`, `VoiceReview`, `Knows`, `OnboardPlan`, `Complete` | `pages/onboarding/wrapper.dart`, `auth.dart`, `ai_consent_widget.dart`, `name/`, `primary_language/`, `permissions/`, `speech_profile_widget.dart`, `guided_voice_*`, `knowledge_graph_step.dart`, `complete_screen.dart` | Welcome: `OmiRingLogo(mode: orbit)` + wordmark. `OnboardPlan` is new and optional (product decision). |
| 16 | Tutorial `TutorialIntro…TutorialDoubleTap` | `pages/onboarding/interactive_device_onboarding/*` | Double-press maps to the local `doubleTapAction` preference. |
| 17 | `Call` | `pages/phone_calls/active_call_page.dart` | |
| 18 | `Startup`, `Gate`, `FirstDay` | app bootstrap / migration gate / Home empty state | |

## Not for Flutter

- `LockScreen`, `HomeScreen`, `Island`, `Icon` boards: iOS system surfaces (Live Activity, WidgetKit) — native Swift in `app/ios`, Android equivalent is the foreground notification.
- `Map`, `Foundations`, `Haptics`, `Motion`, `Flow`, `Scale` boards: reference, not screens.
