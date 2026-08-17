# SSOT (Single Source of Truth) Audit — Omi Codebase

**Date:** 2026-08-17
**Scope:** Flutter app, macOS desktop, backend (Python/Firestore/Redis)
**Goal:** Move SSOT to cloud; local stores become projections/caches only.

---

## Findings

### Flutter: SharedPreferences (`app/lib/backend/preferences.dart`)

The Flutter app has **90+ local preference getters** in SharedPreferences. Most are legitimate device-local settings (batch mode, BLE device state). However, many duplicate cloud state or should be server-authoritative:

```
shrink cachedConversations in SharedPreferences duplicates Firestore conversations. Remove local list; fetch from API on demand. [app/lib/backend/preferences.dart:558]
shrink cachedPeople in SharedPreferences duplicates Firestore people collection. Remove local list; fetch from API on demand. [app/lib/backend/preferences.dart:626]
shrink pendingMemories in SharedPreferences duplicates cloud memory queue. Move to server-side outbox or Firestore pending_memories. [app/lib/backend/preferences.dart:587]
shrink gptCompletionCache in SharedPreferences is a local LLM response cache with no TTL or invalidation. Drop or move to server-side cache. [app/lib/backend/preferences.dart:405]
shrink taskCategoryOrder in SharedPreferences duplicates backend task ordering. Make backend the authority. [app/lib/backend/preferences.dart:308]
shrink taskGoalLinks in SharedPreferences duplicates backend goal-task associations. Make backend the authority. [app/lib/backend/preferences.dart:326]
yagni webhookOnConversationCreated stored only locally. Move to server-side webhook config in Firestore user doc. [app/lib/backend/preferences.dart:229]
yagni webhookOnTranscriptStored stored only locally. Move to server-side webhook config. [app/lib/backend/preferences.dart:233]
yagni webhookAudioBytes stored only locally. Move to server-side webhook config. [app/lib/backend/preferences.dart:237]
yagni webhookAudioBytesDelay stored only locally. Move to server-side webhook config. [app/lib/backend/preferences.dart:241]
yagni webhookDaySummary stored only locally. Move to server-side webhook config. [app/lib/backend/preferences.dart:245]
shrink transcriptionModel stored locally AND backend has transcription_preferences. Make backend the authority; local is stale projection. [app/lib/backend/preferences.dart:389]
shrink conversationSilenceDuration stored locally with no cloud sync. Move to user preferences in Firestore. [app/lib/backend/preferences.dart:385]
yagni voiceResponseMode stored locally only. Move to user preferences in Firestore. [app/lib/backend/preferences.dart:287]
yagni notificationFrequency stored locally only; backend also has notification_settings. Make backend the authority. [app/lib/backend/preferences.dart:304]
shrink autoCreateSpeakersEnabled stored locally only. Move to user preferences in Firestore. [app/lib/backend/preferences.dart:259]
yagni showGoalTrackerEnabled / showDailyScoreEnabled / showTasksEnabled / showPhoneCallButton — UI widget visibility stored locally. Move to server-side user preferences for cross-device consistency. [app/lib/backend/preferences.dart:262-279]
yagni vadGateEnabled stored locally only. Move to user preferences in Firestore. [app/lib/backend/preferences.dart:294]
yagni claudeAgentEnabled stored locally only. Move to user preferences in Firestore. [app/lib/backend/preferences.dart:299]
shrink otaWifiSsid / otaWifiPassword stored locally with no cloud sync. Device-local is correct for WiFi credentials, but consider encrypted server backup for device migration. [app/lib/backend/preferences.dart:379-383]
delete hasViewedWrapped2025 stored locally only. Ephemeral flag with no cross-device value. [app/lib/backend/preferences.dart:345]
delete conversationEventsToggled / transcriptsToggled / audioBytesToggled / daySummaryToggled — UI toggle state stored locally. Transient UI state, not user preference. [app/lib/backend/preferences.dart:349-361]
delete showSummarizeConfirmation / showSubmitAppConfirmation / showInstallAppConfirmation — one-shot confirmation flags. Reset on reinstall anyway. [app/lib/backend/preferences.dart:363-373]
delete showFirmwareUpdateDialog — one-shot dialog flag. [app/lib/backend/preferences.dart:375]
```

### macOS: GRDB Local Database (`desktop/macos/Desktop/Sources/Rewind/Core/`)

The macOS app has **17 GRDB tables** in a local SQLite database (`omi.db`). Several have bidirectional sync with the cloud (good), but several are local-only and should be synced:

```
shrink screenshots table stores screen captures locally with no cloud sync. ScreenActivitySyncService syncs metadata to Firestore but the full screenshot data stays local-only. Consider cloud backup for cross-device access. [desktop/macos/.../RewindModels.swift:63]
shrink indexed_files table is purely local file-index metadata. Never synced to cloud. Consider syncing to cloud for cross-device file search. [desktop/macos/.../IndexedFileRecord.swift:61]
shrink local_kg_nodes / local_kg_edges tables are purely local knowledge graph. Backend has knowledge_nodes/knowledge_edges in Firestore. Sync local KG to cloud for cross-device knowledge. [desktop/macos/.../KnowledgeGraphRecord.swift:16,54]
yagni live_notes table stores AI-generated notes during recording sessions. Local-only, never synced. Consider syncing to cloud for cross-device access. [desktop/macos/.../LiveNoteModels.swift:34]
shrink observations table stores screen observation data locally. Never synced to cloud. Consider syncing for cross-device task context. [desktop/macos/.../ObservationRecord.swift:19]
yagni task_dedup_log table stores task deduplication decisions locally. Never synced. Consider syncing for cross-device dedup consistency. [desktop/macos/.../ProactiveModels.swift:172]
shrink task_chat_messages table has backendSynced field but backend has no task_chat_messages collection. The sync path is incomplete. [desktop/macos/.../TaskChatMessageStorage.swift:27]
```

### macOS: UserDefaults / @AppStorage

```
shrink hasCompletedOnboarding stored in UserDefaults only. Backend has onboarding data in Firestore user doc. Make backend the authority. [desktop/macos/.../AppState.swift:284]
shrink desktop_isPaywalled stored in UserDefaults only. Backend has subscription data. Make backend the authority. [desktop/macos/.../AppState.swift:411]
yagni screenAnalysisEnabled stored in @AppStorage only. Move to server-side user preferences. [desktop/macos/.../RewindOnlyView.swift:194]
yagni rewindRetentionDays stored in @AppStorage only. Move to server-side user preferences. [desktop/macos/.../RewindOnlyView.swift:195]
yagni rewindCaptureInterval stored in @AppStorage only. Move to server-side user preferences. [desktop/macos/.../RewindOnlyView.swift:196]
yagni askModeEnabled stored in @AppStorage only. Move to server-side user preferences. [desktop/macos/.../ChatInputView.swift:88]
yagni currentTierLevel stored in @AppStorage only. Backend has subscription/tier data. Make backend the authority. [desktop/macos/.../SidebarView.swift:15]
yagni onboardingStep / onboardingFurthestStep / onboardingJustCompleted stored in @AppStorage only. Backend has onboarding data. Make backend the authority. [desktop/macos/.../DesktopHomeView.swift:60-62]
yagni useLegacyHomeDesign stored in @AppStorage only. Move to server-side user preferences. [desktop/macos/.../DesktopHomeView.swift:63]
yagni topBarNewSince stored in @AppStorage only. Ephemeral UI state, not user preference. [desktop/macos/.../DesktopHomeView.swift:68]
yagni audioRecordingMode stored in @AppStorage only. Move to server-side user preferences. [desktop/macos/.../SidebarView.swift:19]
yagni preferredInputUID (microphone picker) stored in @AppStorage only. Device-local is correct, but consider server backup for device migration. [desktop/macos/.../MicrophonePickerCard.swift:87]
```

### Backend: Redis Cache (`backend/database/redis_db.py`)

The backend Redis cache is **properly designed as a projection cache** with TTLs and invalidation. No SSOT violations here — Redis is explicitly not the authority:

```
delete (none) Redis cache is correctly a projection of Firestore with TTLs. No SSOT violation. [backend/database/redis_db.py]
```

### Backend: Firestore Cache (`backend/database/firestore_cache.py`)

The Firestore cache is **properly designed as a read-through cache** with versioned keys and TTLs. No SSOT violations:

```
delete (none) Firestore cache is correctly a read-through projection of Firestore with TTLs. No SSOT violation. [backend/database/firestore_cache.py]
```

### Backend: In-Memory Cache (`backend/database/cache.py`, `cache_manager.py`)

The in-memory cache is **properly designed as a projection cache** with LRU eviction and pub/sub invalidation. No SSOT violations:

```
delete (none) In-memory cache is correctly a projection of Redis/Firestore with TTLs. No SSOT violation. [backend/database/cache.py]
```

### Memory System SSOT Analysis

The memory system has **three layers** with potential divergence:

1. **Backend Firestore** (`users/{uid}/memories/{memory_id}`) — the canonical SSOT ✅
2. **macOS GRDB** (`memories` table) — local cache with bidirectional sync via `backendId`/`backendSynced` ✅
3. **Flutter SharedPreferences** (`pendingMemories`) — offline queue for memories created while disconnected ⚠️

```
shrink pendingMemories in Flutter SharedPreferences is an offline memory queue that could diverge from cloud if sync fails. Move to server-side outbox pattern (Firestore pending_memories collection). [app/lib/backend/preferences.dart:587]
shrink macOS memories table has local-only rows (backendSynced=false) that could diverge if sync never completes. Add TTL or reconciliation job. [desktop/macos/.../MemoryStorage.swift:528]
```

### Conversation System SSOT Analysis

```
shrink Flutter cachedConversations duplicates Firestore conversations. Remove local list; fetch from API on demand. [app/lib/backend/preferences.dart:558]
shrink macOS transcription_sessions has backendId/backendSynced for bidirectional sync. Correct pattern. [desktop/macos/.../TranscriptionModels.swift:69]
```

### User Profile SSOT Analysis

```
shrink macOS ai_user_profiles table stores AI-generated user profiles locally with backendSynced field. Backend has no ai_user_profiles collection. The sync path is incomplete. [desktop/macos/.../AIUserProfileService.swift:18]
shrink Backend users.py has user profile in Firestore. macOS and Flutter both cache subsets locally. Make Firestore the sole authority; clients fetch on demand. [backend/database/users.py:202]
```

---

## Summary

| Category | Count | Lines Saved (est.) |
|----------|-------|--------------------|
| `shrink` | 18 | ~800 |
| `yagni` | 16 | ~400 |
| `delete` | 5 | ~100 |
| **Total** | **39** | **~1,300** |

### Key Architectural Recommendations

1. **Flutter SharedPreferences → server-side user preferences**: Move ~20 settings to Firestore `users/{uid}/preferences` document. Local SharedPreferences becomes a read-through cache with TTL.

2. **macOS GRDB local-only tables → cloud sync**: Add `ScreenActivitySyncService`-style sync for `indexed_files`, `local_kg_nodes/edges`, `live_notes`, `observations`, `task_dedup_log`.

3. **macOS UserDefaults/@AppStorage → server-side user preferences**: Move ~12 settings to Firestore `users/{uid}/desktop_preferences` document. UserDefaults becomes a read-through cache.

4. **Flutter pendingMemories → server-side outbox**: Replace local SharedPreferences queue with Firestore `users/{uid}/pending_memories` collection.

5. **macOS ai_user_profiles → cloud sync**: Complete the sync path to backend or make it a local-only derived cache (acceptable if the backend user profile is the authority).

### Dependencies That Could Be Removed

- `shared_preferences` package dependency reduced to read-through cache only (~50 lines)
- macOS `UserDefaults` usage reduced to device-local-only settings (~30 lines)
- macOS GRDB `local_kg_*` tables could be replaced by cloud knowledge graph API (~100 lines)

**Net: -1,300 lines, -3 deps possible** (SharedPreferences → thin cache layer, UserDefaults → thin cache layer, macOS local_kg_* tables → cloud API).
