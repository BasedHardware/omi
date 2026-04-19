# State Management — Omi App

> **Governance:** Any PR that changes provider registrations in `lib/main.dart`,
> adds/removes/renames a provider in `lib/providers/**`, or modifies a `ProxyProvider` chain
> **must** update this file and regenerate `generated/state-management.providers.yaml` via
> `bash scripts/agent/generate_state_graph.sh`.

---

## Table of Contents

1. [Composition Root](#1-composition-root)
2. [Provider Contract Table](#2-provider-contract-table)
3. [ProxyProvider Chains](#3-proxyprovider-chains)
4. [Blast-Radius Table](#4-blast-radius-table)
5. [Mutation Ownership](#5-mutation-ownership)
6. [Cross-Provider Reaction Patterns](#6-cross-provider-reaction-patterns)
7. [Freshness Checklist](#7-freshness-checklist)

---

## 1. Composition Root

All providers are registered in `lib/main.dart` inside a `MultiProvider`.

**Baseline counts:**
- **41 provider registrations** at root
- **9 ProxyProvider** wrappers
- **30+ provider implementation classes** across `lib/providers/` and page-scoped files

### Registration Order Matters

Providers listed higher in `MultiProvider` are available to those listed below. ProxyProviders
that depend on another provider must appear **after** that provider in the list.

```dart
// Simplified structure of lib/main.dart
MultiProvider(
  providers: [
    // Foundation (no deps)
    ChangeNotifierProvider(create: (_) => AuthProvider()),
    ChangeNotifierProvider(create: (_) => ConnectivityProvider()),

    // Device layer (depends on Auth)
    ChangeNotifierProxyProvider<AuthProvider, DeviceProvider>(
      create: (_) => DeviceProvider(),
      update: (_, auth, device) => device!..updateAuth(auth),
    ),

    // Capture (depends on Device + Auth)
    ChangeNotifierProxyProvider2<AuthProvider, DeviceProvider, CaptureProvider>(
      create: (_) => CaptureProvider(),
      update: (_, auth, device, capture) => capture!..update(auth, device),
    ),

    // Conversation (depends on Auth + Capture)
    ChangeNotifierProxyProvider2<AuthProvider, CaptureProvider, ConversationProvider>(...),

    // Home (depends on Conversation + Capture + Device)
    ChangeNotifierProxyProvider3<ConversationProvider, CaptureProvider, DeviceProvider, HomeProvider>(...),

    // Chat, Memories, Apps, ActionItems, Settings ...
    // (see full list in lib/main.dart)
  ],
)
```

---

## 2. Provider Contract Table

> Format: Provider name | Class | File | Source-of-truth fields | Key mutators | Disposed?

### Foundation Providers

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Auth | `AuthProvider` | `lib/providers/auth_provider.dart` | `user`, `isSignedIn`, `accessToken` | `signIn()`, `signOut()`, `refreshToken()` |
| Connectivity | `ConnectivityProvider` | `lib/providers/connectivity_provider.dart` | `isConnected`, `connectionType` | Auto-updated by `connectivity_plus` stream |

### Device Providers

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Device | `DeviceProvider` | `lib/providers/device_provider.dart` | `connectedDevice`, `batteryLevel`, `firmwareVersion`, `scanResults` | `startBLEScan()`, `connectToDevice()`, `disconnectDevice()` |

### Capture Providers

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Capture | `CaptureProvider` | `lib/providers/capture_provider.dart` | `segments`, `captureSessionState`, `socketStatus`, `audioLevel` | `startCapture()`, `stopCapture()`, `handleWebSocketEvent()` |

### Conversation Providers

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Conversation | `ConversationProvider` | `lib/providers/conversation_provider.dart` | `conversations`, `selectedConversation`, `loadingState` | `fetchConversations()`, `loadConversation()`, `updateConversation()`, `deleteConversation()` |

### App / Integration Providers

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Apps | `AppProvider` | `lib/providers/app_provider.dart` | `apps`, `installedApps`, `loadingState` | `fetchApps()`, `installApp()`, `uninstallApp()` |

### Memory Providers

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Memories | `MemoryProvider` | `lib/providers/memory_provider.dart` | `memories`, `loadingState` | `fetchMemories()`, `createMemory()`, `updateMemory()`, `deleteMemory()` |

### Chat Providers

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Chat | `ChatProvider` | `lib/providers/chat_provider.dart` | `messages`, `threadId`, `streamingState` | `sendMessage()`, `loadThread()`, `clearThread()` |

### Action Item Providers

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Action Items | `ActionItemsProvider` | `lib/providers/action_items_provider.dart` | `actionItems`, `loadingState` | `fetchActionItems()`, `updateActionItem()`, `deleteActionItem()` |

### Home Aggregator

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Home | `HomeProvider` | `lib/providers/home_provider.dart` | `selectedTab`, `badgeCounts`, `syncStatus` | `setTab()`, `refreshAll()` |

### Settings / User

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Settings | `SettingsProvider` | `lib/providers/settings_provider.dart` | `notificationsEnabled`, `selectedLanguage`, `privacySettings` | `updateSetting()`, `resetToDefaults()` |

### Payments

| Provider | Class | File | Key state fields | Key mutators |
|---|---|---|---|---|
| Subscription | `SubscriptionProvider` | `lib/providers/subscription_provider.dart` | `plan`, `isActive`, `expiresAt` | `fetchSubscription()`, `initCheckout()` |

---

## 3. ProxyProvider Chains

ProxyProviders inject upstream state into downstream providers. The `update` callback is called
whenever an upstream provider notifies.

```
AuthProvider
  ├──► DeviceProvider         (via ChangeNotifierProxyProvider)
  ├──► CaptureProvider        (via ChangeNotifierProxyProvider2 with DeviceProvider)
  ├──► ConversationProvider   (via ChangeNotifierProxyProvider2 with CaptureProvider)
  ├──► ChatProvider           (via ChangeNotifierProxyProvider)
  ├──► MemoryProvider         (via ChangeNotifierProxyProvider)
  ├──► AppProvider            (via ChangeNotifierProxyProvider)
  ├──► ActionItemsProvider    (via ChangeNotifierProxyProvider)
  ├──► SubscriptionProvider   (via ChangeNotifierProxyProvider)
  └──► SettingsProvider       (via ChangeNotifierProxyProvider)

DeviceProvider
  └──► CaptureProvider        (auth token + device reference for socket auth)

CaptureProvider
  └──► ConversationProvider   (new conversation ID from capture events)

ConversationProvider
└──► HomeProvider             (conversation list for badge counts)
CaptureProvider
└──► HomeProvider             (capture status for header indicator)
DeviceProvider
└──► HomeProvider             (device connection state for header icon)
```

---

## 4. Blast-Radius Table

A change to a provider's public API or notification behavior can force rebuilds in all
consumers. The table below shows the **direct dependent file count** for each high-impact
provider.

| Provider | Direct dependents (files) | Blast notes |
|---|---|---|
| `AppProvider` | ~31 | Widest blast radius; Apps tab + settings + onboarding all watch it |
| `HomeProvider` | ~22 | Root scaffold + all tab pages watch it for badge/nav state |
| `CaptureProvider` | ~19 | Capture page + conversation + home header + device indicator |
| `ConversationProvider` | ~19 | Conversations list, detail, home aggregator, action items |
| `DeviceProvider` | ~18 | Capture, home header, settings device page, onboarding |
| `AuthProvider` | ~15 | All ProxyProvider chains; sign-in/out triggers full tree rebuild |
| `ChatProvider` | ~10 | Chat tab only; lower risk |
| `MemoryProvider` | ~9 | Memories tab only; lower risk |
| `ActionItemsProvider` | ~8 | Action items page + conversation detail |
| `SubscriptionProvider` | ~6 | Settings + paywall guards |

**High-risk change rule:** Any mutation to `AppProvider`, `HomeProvider`, `CaptureProvider`,
`ConversationProvider`, or `DeviceProvider` public API requires review from a maintainer and
must include regression tests.

---

## 5. Mutation Ownership

**Single source of truth rule:** Each piece of app state has exactly one owning provider.
No other provider or widget should modify that state directly.

| State domain | Owning provider | Mutation entry point |
|---|---|---|
| Authenticated user / tokens | `AuthProvider` | `signIn()`, `signOut()`, `refreshToken()` |
| BLE device connection | `DeviceProvider` | `connectToDevice()`, `disconnectDevice()` |
| Active capture session | `CaptureProvider` | `startCapture()`, `stopCapture()` |
| Conversation list + detail | `ConversationProvider` | `fetchConversations()`, `updateConversation()` |
| Chat thread messages | `ChatProvider` | `sendMessage()`, `loadThread()` |
| Memory list | `MemoryProvider` | `fetchMemories()`, `createMemory()` |
| Installed apps | `AppProvider` | `installApp()`, `uninstallApp()` |
| Action items | `ActionItemsProvider` | `fetchActionItems()`, `updateActionItem()` |
| Active tab / nav state | `HomeProvider` | `setTab()` |
| User preferences / settings | `SettingsProvider` | `updateSetting()` |
| Subscription plan | `SubscriptionProvider` | `fetchSubscription()` |

---

## 6. Cross-Provider Reaction Patterns

These are the runtime reactions that cross provider boundaries. They are **not** ProxyProvider
wires — they happen via `addListener` or direct calls inside `update` callbacks.

| Trigger | Reaction | Implementation |
|---|---|---|
| `AuthProvider.signOut()` | All providers clear their cached state | Each ProxyProvider `update()` checks `auth.isSignedIn`; calls `clear()` if false |
| `DeviceProvider` disconnect event | `CaptureProvider.stopCapture()` called | `CaptureProvider.update()` watches `device.connectedDevice` |
| `CaptureProvider` emits `conversationCreated` | `ConversationProvider.prependDraft()` | `ConversationProvider.update()` consumes `capture.pendingConversationId` |
| `ConversationProvider` list changes | `HomeProvider` updates badge count | `HomeProvider.update()` reads `conversation.unreadCount` |
| `AppProvider` install completes | `HomeProvider` refreshes app badge | `HomeProvider.update()` reads `app.hasUpdates` |

---

## 7. Freshness Checklist

When updating this file, verify:

- [ ] Any new provider has a row in §2.
- [ ] Any removed provider has its row deleted and blast-radius table updated.
- [ ] Any new ProxyProvider dependency is reflected in §3.
- [ ] Blast-radius counts in §4 are re-estimated after significant refactoring.
- [ ] Mutation ownership table in §5 has no gaps (every stateful domain is covered).
- [ ] `generated/state-management.providers.yaml` regenerated via `bash scripts/agent/generate_state_graph.sh`.
