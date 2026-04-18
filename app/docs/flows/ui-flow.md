# UI Flow — Omi App

> **Governance:** Any PR that changes navigation, adds/removes screens, or alters route behavior
> in `lib/pages/**` or `lib/core/app_shell.dart` **must** update this file and regenerate
> `generated/ui-flow.screens.yaml` via `bash scripts/agent/generate_ui_flow_index.sh`.

---

## Table of Contents

1. [Flow Groups Overview](#1-flow-groups-overview)
2. [Screen Registry](#2-screen-registry)
3. [Navigation Graph](#3-navigation-graph)
4. [Deep-Link & Notification Entry Points](#4-deep-link--notification-entry-points)
5. [Shared Component Map](#5-shared-component-map)
6. [Freshness Checklist](#6-freshness-checklist)

---

## 1. Flow Groups Overview

| # | Flow Group | Screen count (baseline) | Entry point |
|---|---|---|---|
| 1 | Onboarding / Auth | ~12 | App cold start (unauthenticated) |
| 2 | Home / Conversations | ~14 | `HomeProvider` scaffold |
| 3 | Chat (AI assistant) | ~8 | Bottom nav tab or deep link |
| 4 | Capture / Recording | ~10 | Foreground service start; BLE connect |
| 5 | Action Items | ~8 | Conversation detail → action items |
| 6 | Memories | ~10 | Bottom nav tab |
| 7 | Apps / Integrations | ~14 | Settings → Apps |
| 8 | Settings | ~18 | Bottom nav tab |
| 9 | Device Sync | ~8 | Onboarding step or Settings |
| 10 | Payments / Subscription | ~6 | Settings → Subscription |

**Total baseline:** ~108 screens across 10 flow groups.

---

## 2. Screen Registry

> Format: `Screen Name | Class | File path | Flow group | Notes`

### 2.1 Onboarding / Auth

| Screen Name | Class | File path | Flow | Notes |
|---|---|---|---|---|
| Splash | `SplashPage` | `lib/pages/splash/page.dart` | Onboarding | First frame; auth gate |
| Auth / Sign In | `SignInPage` | `lib/pages/auth/page.dart` | Onboarding | Google / Apple OAuth |
| Onboarding Welcome | `OnboardingWelcomePage` | `lib/pages/onboarding/welcome/page.dart` | Onboarding | |
| Onboarding Permissions | `OnboardingPermissionsPage` | `lib/pages/onboarding/permissions/page.dart` | Onboarding | Mic, BT, notifications |
| Onboarding Device Pairing | `OnboardingDevicePage` | `lib/pages/onboarding/device/page.dart` | Onboarding | BLE scan + connect |
| Onboarding Name | `OnboardingNamePage` | `lib/pages/onboarding/name/page.dart` | Onboarding | Profile setup |
| Onboarding Complete | `OnboardingCompletePage` | `lib/pages/onboarding/complete/page.dart` | Onboarding | Transition to Home |

### 2.2 Home / Conversations

| Screen Name | Class | File path | Flow | Notes |
|---|---|---|---|---|
| Home Shell | `HomePageWrapper` | `lib/pages/home/page.dart` | Home | Root scaffold + bottom nav |
| Conversations List | `ConversationsPage` | `lib/pages/conversations/page.dart` | Home | Paginated list |
| Conversation Detail | `ConversationDetailPage` | `lib/pages/conversations/detail/page.dart` | Home | Transcript + summary |
| Conversation Edit | `ConversationEditPage` | `lib/pages/conversations/edit/page.dart` | Home | Edit title/summary |

### 2.3 Chat

| Screen Name | Class | File path | Flow | Notes |
|---|---|---|---|---|
| Chat List | `ChatPage` | `lib/pages/chat/page.dart` | Chat | AI assistant tab |
| Chat Thread | `ChatThreadPage` | `lib/pages/chat/thread/page.dart` | Chat | Message thread |

### 2.4 Capture / Recording

| Screen Name | Class | File path | Flow | Notes |
|---|---|---|---|---|
| Capture (active) | `CapturePage` | `lib/pages/capture/page.dart` | Capture | Real-time transcript |

### 2.5 Action Items

| Screen Name | Class | File path | Flow | Notes |
|---|---|---|---|---|
| Action Items List | `ActionItemsPage` | `lib/pages/action_items/page.dart` | Action Items | Aggregated across conversations |

### 2.6 Memories

| Screen Name | Class | File path | Flow | Notes |
|---|---|---|---|---|
| Memories List | `MemoriesPage` | `lib/pages/memories/page.dart` | Memories | |
| Memory Detail | `MemoryDetailPage` | `lib/pages/memories/detail/page.dart` | Memories | |
| Memory Edit | `MemoryEditPage` | `lib/pages/memories/edit/page.dart` | Memories | |

### 2.7 Apps / Integrations

| Screen Name | Class | File path | Flow | Notes |
|---|---|---|---|---|
| Apps Marketplace | `AppsPage` | `lib/pages/apps/page.dart` | Apps | Browse + install |
| App Detail | `AppDetailPage` | `lib/pages/apps/detail/page.dart` | Apps | |
| App Install Confirm | `AppInstallPage` | `lib/pages/apps/install/page.dart` | Apps | Permissions grant |

### 2.8 Settings

| Screen Name | Class | File path | Flow | Notes |
|---|---|---|---|---|
| Settings Root | `SettingsPage` | `lib/pages/settings/page.dart` | Settings | |
| Profile | `ProfilePage` | `lib/pages/settings/profile/page.dart` | Settings | |
| Notifications | `NotificationsSettingsPage` | `lib/pages/settings/notifications/page.dart` | Settings | |
| Privacy | `PrivacyPage` | `lib/pages/settings/privacy/page.dart` | Settings | |
| Developer | `DeveloperPage` | `lib/pages/settings/developer/page.dart` | Settings | Debug/dev only |
| About | `AboutPage` | `lib/pages/settings/about/page.dart` | Settings | |

### 2.9 Device Sync

| Screen Name | Class | File path | Flow | Notes |
|---|---|---|---|---|
| Device Selection | `DeviceSelectionPage` | `lib/pages/settings/device/page.dart` | Device Sync | BLE scan |
| Device Info | `DeviceInfoPage` | `lib/pages/settings/device/info/page.dart` | Device Sync | Firmware, battery |

### 2.10 Payments / Subscription

| Screen Name | Class | File path | Flow | Notes |
|---|---|---|---|---|
| Subscription Plans | `SubscriptionPage` | `lib/pages/settings/subscription/page.dart` | Payments | |
| Payment Success | `PaymentSuccessPage` | `lib/pages/settings/subscription/success/page.dart` | Payments | |

---

## 3. Navigation Graph

### Root Shell

```
App start
  ├── [unauthenticated] → SplashPage → AuthPage → OnboardingWelcomePage → ... → HomeShell
  └── [authenticated]   → SplashPage → HomeShell
```

### HomeShell Bottom Nav (4 tabs)

```
HomeShell
  ├── tab[0] ConversationsPage
  │         └── ConversationDetailPage
  │                  └── ConversationEditPage
  ├── tab[1] CapturePage
  ├── tab[2] ChatPage
  │         └── ChatThreadPage
  └── tab[3] SettingsPage
            ├── ProfilePage
            ├── NotificationsSettingsPage
            ├── PrivacyPage
            ├── DeviceSelectionPage → DeviceInfoPage
            ├── SubscriptionPage → PaymentSuccessPage
            ├── AppsPage → AppDetailPage → AppInstallPage
            ├── MemoriesPage → MemoryDetailPage → MemoryEditPage
            └── DeveloperPage (dev flavor only)
```

### Action Items (cross-flow)

```
ConversationDetailPage  ──►  ActionItemsPage
CapturePage             ──►  ActionItemsPage
```

---

## 4. Deep-Link & Notification Entry Points

| Scheme / Pattern | Destination screen | Handler location |
|---|---|---|
| `omi://conversation/<id>` | `ConversationDetailPage` | `lib/core/app_shell.dart` |
| `omi://memory/<id>` | `MemoryDetailPage` | `lib/core/app_shell.dart` |
| `omi://apps/<id>` | `AppDetailPage` | `lib/core/app_shell.dart` |
| `omi://chat` | `ChatPage` | `lib/core/app_shell.dart` |
| Push notification: `type=conversation` | `ConversationDetailPage` | `lib/services/notifications.dart` |
| Push notification: `type=action_item` | `ActionItemsPage` | `lib/services/notifications.dart` |
| Push notification: `type=memory` | `MemoryDetailPage` | `lib/services/notifications.dart` |
| Universal link (web fallback) | `HomeShell` | `lib/core/app_shell.dart` |

---

## 5. Shared Component Map

| Component | Class | Path | Used in flows |
|---|---|---|---|
| App Shell / Root | `AppShell` | `lib/core/app_shell.dart` | All |
| Bottom Navigation Bar | `HomeBottomNavBar` | `lib/widgets/home/nav_bar.dart` | Home, Chat, Settings |
| Transcript Widget | `TranscriptWidget` | `lib/widgets/transcript/` | Capture, Conversation Detail |
| App Tile | `AppTile` | `lib/widgets/apps/app_tile.dart` | Apps, Settings |
| Memory Card | `MemoryCard` | `lib/widgets/memories/card.dart` | Memories |
| Action Item Row | `ActionItemRow` | `lib/widgets/action_items/row.dart` | Action Items, Conversation Detail |
| Loading / Spinner | `OmiCircularProgress` | `lib/widgets/common/progress.dart` | All |

---

## 6. Freshness Checklist

When updating this file, verify:

- [ ] Every new `lib/pages/**` file has a row in the Screen Registry.
- [ ] Any renamed class or file has its row updated.
- [ ] Navigation graph reflects current `GoRouter` / `Navigator.push` call graph.
- [ ] Deep-link table matches entries in `lib/core/app_shell.dart` and `lib/services/notifications.dart`.
- [ ] `generated/ui-flow.screens.yaml` regenerated via `bash scripts/agent/generate_ui_flow_index.sh`.
