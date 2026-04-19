# Data Flow — Omi App

> **Governance:** Any PR that changes `lib/backend/http/api/**`, `lib/backend/schema/**`,
> `lib/services/sockets/**`, or deep-link/notification handlers **must** update this file and
> regenerate `generated/data-flow.inventory.yaml` via
> `bash scripts/agent/generate_data_flow_inventory.sh`.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [API Layer Structure](#2-api-layer-structure)
3. [Core Flow Traces](#3-core-flow-traces)
   - [3.1 Auth Flow](#31-auth-flow)
   - [3.2 Conversation Capture Flow](#32-conversation-capture-flow)
   - [3.3 Conversation Processing Flow](#33-conversation-processing-flow)
   - [3.4 Chat / AI Assistant Flow](#34-chat--ai-assistant-flow)
   - [3.5 App Install Flow](#35-app-install-flow)
   - [3.6 Action Items Flow](#36-action-items-flow)
   - [3.7 Device Connection Flow](#37-device-connection-flow)
   - [3.8 Deep-Link / Notification Routing Flow](#38-deep-link--notification-routing-flow)
4. [WebSocket Event Surface](#4-websocket-event-surface)
5. [Error and Fallback Paths](#5-error-and-fallback-paths)
6. [Freshness Checklist](#6-freshness-checklist)

---

## 1. Architecture Overview

```
UI Layer (lib/pages/**)
     │  context.watch / Consumer
     ▼
Provider Layer (lib/providers/**)
     │  calls
     ▼
API Client Layer (lib/backend/http/api/**)
     │  http / dio
     ▼
Omi Backend (HTTPS REST + WSS)
     │
     ▼
Schema Layer (lib/backend/schema/**)   ← model transform on response
```

WebSocket path:

```
CaptureProvider / ChatProvider
     │  opens
     ▼
lib/services/sockets/** (WebSocketManager)
     │  wss://
     ▼
Omi Backend (Pusher / Listen endpoint)
     │  events →  MessageEvent (typed)
     ▼
Provider dispatch → UI rebuild
```

---

## 2. API Layer Structure

**Base module path:** `lib/backend/http/api/`

| Module | File | Responsibility |
|---|---|---|
| Auth | `auth.dart` | Sign-in, sign-out, token refresh, account management |
| Conversations | `conversations.dart` | CRUD for conversation records |
| Memories | `memories.dart` | CRUD for memory entries |
| Chat | `chat.dart` | Send message, list threads, delete thread |
| Apps | `apps.dart` | List, install, uninstall, update app integrations |
| Action Items | `action_items.dart` | List, update, delete action items |
| Devices | `devices.dart` | Register device, list devices, delete device |
| Notifications | `notifications.dart` | Register FCM token, update push prefs |
| User | `users.dart` | Get/update profile, delete account |
| Webhooks | `webhooks.dart` | Create/list/delete webhook endpoints |
| Payments | `payments.dart` | Subscription status, initiate checkout |
| Processing Audio | `processing_memories.dart` | Upload offline audio for processing |
| Speech Profile | `speech_profile.dart` | Create/update speaker voice profile |
| Search | `search.dart` | Full-text search across conversations + memories |
| Facts | `facts.dart` | User-defined facts / profile facts |
| AI API | `openai.dart` | Proxied completions for in-app AI features |
| Personas | `personas.dart` | Manage AI persona configurations |
| Trends | `trends.dart` | Aggregate usage trends for dashboard |
| Plugins (v2) | `plugins.dart` | Plugin marketplace listing and management |
| Workflow | `workflow.dart` | Trigger and status for async processing jobs |
| Geolocation | `geolocation.dart` | Update last-known location for context |
| Calendar | `calendar.dart` | Calendar event fetch for context injection |
| Feedback | `feedback.dart` | Submit in-app feedback / bug reports |
| Misc | `misc.dart` | Health check, version check, feature flags |

**Total: 24 API client modules, ~132 unique endpoint path patterns.**

---

## 3. Core Flow Traces

### 3.1 Auth Flow

```
SplashPage
  └─ AuthProvider.checkAuthState()
       ├─ [token valid] → navigate to HomeShell
       └─ [no token / expired] → navigate to AuthPage
            └─ User taps "Sign in with Google"
                 └─ google_sign_in package → OAuth token
                      └─ api/auth.dart: POST /v1/auth/google
                           └─ Response: {access_token, refresh_token, user}
                                └─ SecureStorage.write(tokens)
                                     └─ AuthProvider.setUser(user)
                                          └─ navigate to OnboardingWelcomePage (new) or HomeShell (returning)
```

**Token refresh path:**
```
Any API call → 401
  └─ api/auth.dart: POST /v1/auth/refresh  {refresh_token}
       ├─ 200: update stored access_token → retry original request
       └─ 401: AuthProvider.signOut() → clear storage → navigate to AuthPage
```

---

### 3.2 Conversation Capture Flow

```
User connects Omi device (BLE)
  └─ DeviceProvider.connectToDevice()
       └─ BLE audio stream → WebSocketManager.openCaptureSocket()
            └─ wss://<backend>/v1/listen
                 └─ Binary audio frames sent continuously
                      └─ Server sends back MessageEvent (typed)
                           └─ CaptureProvider.handleWebSocketEvent(event)
                                ├─ TranscriptSegmentEvent → update live transcript UI
                                ├─ ConversationCreatedEvent → create local draft
                                └─ ConversationProcessingEvent → show "processing" state
```

---

### 3.3 Conversation Processing Flow

```
Recording ends (BLE disconnect or manual stop)
  └─ CaptureProvider.stopCapture()
       └─ WebSocketManager.closeCaptureSocket()
            └─ Server finalizes conversation
                 └─ Push notification: type=conversation (or polling)
                      └─ ConversationProvider.fetchConversations()
                           └─ api/conversations.dart: GET /v1/conversations
                                └─ List<Conversation> (schema: lib/backend/schema/conversation.dart)
                                     └─ ConversationProvider.setState(conversations)
                                          └─ ConversationsPage rebuilds
```

**Offline audio upload path:**
```
User has offline audio file
  └─ api/processing_memories.dart: POST /v1/processing-memories  {audio_file}
       └─ Returns {job_id}
            └─ Poll api/workflow.dart: GET /v1/workflow/{job_id}
                 └─ On complete: ConversationProvider.fetchConversations()
```

---

### 3.4 Chat / AI Assistant Flow

```
User types message in ChatThreadPage
  └─ ChatProvider.sendMessage(text)
       └─ api/chat.dart: POST /v1/chat  {message, thread_id?}
            ├─ [streaming response] WebSocket event stream → token-by-token render
            └─ [non-streaming] Response: {reply, thread_id}
                 └─ ChatProvider.appendMessage(reply)
                      └─ ChatThreadPage rebuilds
```

---

### 3.5 App Install Flow

```
AppsPage loads
  └─ AppsProvider.fetchApps()
       └─ api/apps.dart: GET /v1/apps
            └─ List<AppModel> (schema: lib/backend/schema/app.dart)
                 └─ AppsPage renders tiles

User taps install on AppDetailPage
  └─ AppsProvider.installApp(appId)
       └─ api/apps.dart: POST /v1/apps/{appId}/install
            └─ 200 → AppsProvider.markInstalled(appId)
                 └─ AppDetailPage shows "Installed" state
```

---

### 3.6 Action Items Flow

```
ConversationDetailPage opens
  └─ ConversationProvider.fetchActionItems(conversationId)
       └─ api/action_items.dart: GET /v1/conversations/{id}/action-items
            └─ List<ActionItem> (schema: lib/backend/schema/action_item.dart)
                 └─ ConversationDetailPage / ActionItemsPage renders rows

User checks off action item
  └─ ActionItemsProvider.updateActionItem(id, completed: true)
       └─ api/action_items.dart: PATCH /v1/action-items/{id}  {completed: true}
            └─ Optimistic local update → server confirm or rollback on error
```

---

### 3.7 Device Connection Flow

```
DeviceSelectionPage
  └─ DeviceProvider.startBLEScan()
       └─ FlutterBluePlus.startScan()
            └─ Discovered devices → DeviceProvider.discoveredDevices list

User selects device
  └─ DeviceProvider.connectToDevice(deviceId)
       └─ FlutterBluePlus.connect(device)
            └─ Characteristic subscription (audio + status)
                 └─ api/devices.dart: POST /v1/devices  {device_id, platform}
                      └─ Device registered → DeviceProvider.connectedDevice = device
```

---

### 3.8 Deep-Link / Notification Routing Flow

```
Incoming deep link (omi://conversation/123) or push notification tap
  └─ lib/core/app_shell.dart: _handleLink(uri)
       └─ Parse route pattern
            ├─ /conversation/<id> → Navigator.push(ConversationDetailPage(id))
            ├─ /memory/<id>      → Navigator.push(MemoryDetailPage(id))
            ├─ /apps/<id>        → Navigator.push(AppDetailPage(id))
            └─ /chat             → HomeShell.switchTab(chatTab)
```

---

## 4. WebSocket Event Surface

**Socket:** `lib/services/sockets/`

All events are deserialized via `MessageEvent.fromJson()` in `lib/backend/schema/message_event.dart`.

| Event type | Dart constant | Payload fields | Consumer |
|---|---|---|---|
| `transcript_segment` | `MessageEventType.transcriptSegment` | `text`, `speaker`, `is_final`, `start`, `end` | `CaptureProvider` → live transcript |
| `conversation_created` | `MessageEventType.conversationCreated` | `conversation_id`, `title` | `CaptureProvider` → draft creation |
| `conversation_processing` | `MessageEventType.conversationProcessing` | `conversation_id`, `status` | `CaptureProvider` → status banner |
| `conversation_processed` | `MessageEventType.conversationProcessed` | `conversation_id` | `ConversationProvider` → refresh list |
| `memory_created` | `MessageEventType.memoryCreated` | `memory_id`, `text` | `MemoriesProvider` → prepend |
| `memory_updated` | `MessageEventType.memoryUpdated` | `memory_id`, `text` | `MemoriesProvider` → update item |
| `action_item_created` | `MessageEventType.actionItemCreated` | `action_item_id`, `text`, `conversation_id` | `ActionItemsProvider` → prepend |
| `chat_message` | `MessageEventType.chatMessage` | `content`, `thread_id`, `is_partial` | `ChatProvider` → stream token |
| `device_battery` | `MessageEventType.deviceBattery` | `level`, `charging` | `DeviceProvider` → battery indicator |
| `device_firmware_update` | `MessageEventType.deviceFirmwareUpdate` | `version`, `url` | `DeviceProvider` → update prompt |
| `error` | `MessageEventType.error` | `code`, `message` | `CaptureProvider` → error banner |
| `ping` | `MessageEventType.ping` | — | `WebSocketManager` → send pong |
| `unknown` | `MessageEventType.unknown` | raw JSON | Logged; no UI action |

**Total: 13 typed events + 1 unknown fallback.**

---

## 5. Error and Fallback Paths

| Scenario | Behaviour | Code location |
|---|---|---|
| HTTP 401 on any API call | Token refresh attempt; sign-out on second 401 | `lib/backend/http/api/_client.dart` |
| HTTP 5xx | Throw `ApiException`; provider shows error state; no silent retry | All API modules |
| WebSocket disconnect (capture) | `CaptureProvider` sets `socketStatus = disconnected`; auto-reconnect after 3s (max 3 attempts) | `lib/services/sockets/capture_socket.dart` |
| WebSocket disconnect (chat stream) | `ChatProvider` marks message as `partial`; user can retry | `lib/services/sockets/chat_socket.dart` |
| BLE connection lost mid-capture | `DeviceProvider.onDisconnect()` → `CaptureProvider.stopCapture()` → conversation finalized server-side | `lib/providers/device_provider.dart` |
| Offline audio upload timeout | `WorkflowProvider.pollJob()` retries up to 5× with exponential back-off | `lib/providers/processing_provider.dart` |
| Deep-link with unknown route | Log warning; navigate to HomeShell root; no crash | `lib/core/app_shell.dart` |
| Push notification with missing `type` | Silently ignored; FCM ack sent | `lib/services/notifications.dart` |

---

## 6. Freshness Checklist

When updating this file, verify:

- [ ] Any new API endpoint has a row in §2 and/or a flow trace in §3.
- [ ] Any removed or renamed endpoint has its row deleted/updated.
- [ ] Any new WebSocket event type has a row in §4.
- [ ] Error table in §5 reflects current retry/fallback logic.
- [ ] `generated/data-flow.inventory.yaml` regenerated via `bash scripts/agent/generate_data_flow_inventory.sh`.
