# Desktop Cross-Platform Migration Tracker

Migration from macOS-only Swift/SwiftUI app (`desktop/`) to cross-platform Tauri 2.0 + React (`desktop-v2/`).

**Tech Stack:** Tauri 2.0 | React 19 + TypeScript + Vite | Existing Rust backend (Axum) | pnpm

## Phase 0: Foundation - COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| Tauri project scaffolding | Done | React + TS + Vite, pnpm |
| Rust backend as library crate | Done | Added `lib.rs` with `init_services()` + `build_router()` |
| Embed backend in Tauri process | Done | Spawns Axum on `127.0.0.1:10201` via path dependency |
| Firebase auth (OAuth flow) | Scaffold | Commands created, wiring to backend OAuth pending |
| Tauri plugins installed | Done | shell, store, notification, global-shortcut, autostart |
| Capabilities configured | Done | `src-tauri/capabilities/default.json` |
| Build verification (Linux) | Done | `cargo check` passes, `pnpm build` passes, `.deb` builds |

## Phase 1: Core UI - COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| Sidebar navigation | Done | `Sidebar.tsx` with NavLink routing |
| Chat page | Done | Message list, streaming indicator, input bar |
| Conversations page | Done | Split-panel: list + detail with transcript |
| Tasks page | Done | Grouped by status, checkbox toggle |
| Memories page | Done | Grid layout with cards |
| Settings page | Done | Account info, placeholder sections |
| Zustand stores | Done | chatStore, conversationStore, taskStore, memoryStore |
| API client | Done | Auto-injects auth token from store |
| React Router | Done | BrowserRouter with 5 routes |

## Phase 2: Audio Capture - COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| Audio capture plugin | Done | `tauri-plugin-audio-capture` using `cpal` crate |
| Device enumeration | Done | Lists input devices cross-platform |
| Microphone capture | Done | 16kHz mono PCM with resampling + channel mixing |
| Audio level metering | Done | RMS + peak calculation |
| Plugin commands | Done | list_devices, start/stop_recording, get_capture_state |

## Phase 3: Screen Capture - COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| Screen capture plugin | Done | `tauri-plugin-screen-capture` |
| Linux capture (X11) | Done | Full implementation via `x11rb` |
| macOS/Windows capture | Stub | Returns "not implemented" (to be added) |
| Active window detection (Linux) | Done | `_NET_ACTIVE_WINDOW` + `WM_NAME` + `WM_CLASS` |
| Active window (macOS/Windows) | Stub | To be added |
| Continuous capture loop | Done | Configurable interval, atomic stop flag |
| Plugin commands | Done | take_screenshot, start/stop, get_active_window_info |

## Phase 4: System Integration - COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| System tray | Ready | `tauri-plugin-notification` installed + configured |
| Global shortcuts | Ready | `tauri-plugin-global-shortcut` with `Cmd+\` / `Ctrl+\` |
| Notifications | Ready | `tauri-plugin-notification` with permission flow |
| Autostart | Ready | `tauri-plugin-autostart` with LaunchAgent (macOS) |
| Capabilities file | Done | All permissions declared in `default.json` |
| JS service wrappers | Done | shortcuts.ts, notifications.ts, autostart.ts |

## Phase 5: Production Hardening - PENDING

| Task | Status | Notes |
|------|--------|-------|
| macOS screen capture (ScreenCaptureKit) | Pending | Requires `objc2` FFI |
| Windows screen capture (DXGI) | Pending | Requires `windows-rs` |
| OCR + indexing | Pending | Tesseract or platform-specific |
| Video chunk encoding | Pending | ffmpeg integration |
| Rewind timeline UI | Pending | React component |
| SQLite database | Pending | `rusqlite` with same schema |
| BLE device support | Pending | `btleplug` crate |
| Proactive assistants | Pending | Port from Swift |
| Auto-updater | Pending | `tauri-plugin-updater` |
| Data migration | Pending | Import from Swift app's GRDB |
| CI matrix | Pending | GitHub Actions for macOS/Win/Linux |
| Installer packaging | Pending | `.dmg` / `.msi` / `.deb` / `.AppImage` |

## Feature Parity Matrix

| Feature | Phase | macOS | Windows | Linux |
|---------|-------|-------|---------|-------|
| **Auth & Session** | | | | |
| Firebase Auth (OAuth) | 0 | Scaffold | Scaffold | Scaffold |
| Token persistence | 0 | Done | Done | Done |
| **Core UI** | | | | |
| Sidebar navigation | 1 | Done | Done | Done |
| Chat + LLM streaming | 1 | Done | Done | Done |
| Conversations list/detail | 1 | Done | Done | Done |
| Tasks CRUD | 1 | Done | Done | Done |
| Memories list | 1 | Done | Done | Done |
| Settings | 1 | Done | Done | Done |
| **Audio** | | | | |
| Microphone capture | 2 | Done | Done | Done |
| Audio level metering | 2 | Done | Done | Done |
| **Screen Capture** | | | | |
| Screen capture | 3 | Stub | Stub | Done |
| Active window detection | 3 | Stub | Stub | Done |
| **System Integration** | | | | |
| Global shortcuts | 4 | Done | Done | Done |
| Notifications | 4 | Done | Done | Done |
| Launch at login | 4 | Done | Done | Done |

## Architecture

```
desktop-v2/
  src/                          # React frontend (TypeScript)
    components/
      sidebar/Sidebar.tsx       # Navigation sidebar
      chat/ChatPage.tsx         # AI chat interface
      conversations/            # Conversation list + detail
      tasks/TasksPage.tsx       # Task management
      memories/MemoriesPage.tsx # Memory cards
      settings/SettingsPage.tsx # Settings
    stores/                     # Zustand state (auth, chat, conversations, tasks, memories)
    services/                   # API client, shortcuts, notifications, autostart
    styles/globals.css          # Dark theme CSS
  src-tauri/
    src/main.rs                 # Tauri entry + embedded Axum backend
    src/commands/auth.rs        # Auth IPC commands
    plugins/
      tauri-plugin-audio-capture/   # cpal-based cross-platform audio
      tauri-plugin-screen-capture/  # X11 (Linux), stubs (macOS/Win)
    capabilities/default.json   # Plugin permissions
```

## Key Decisions

| Decision | Rationale | Date |
|----------|-----------|------|
| Tauri 2.0 over Electron | Performance (no Chromium), Rust-native, backend embeds directly | 2026-04-12 |
| React over Vue/Svelte | Consistent with existing web app, shadcn/ui reuse | 2026-04-12 |
| pnpm over npm/yarn | Team preference | 2026-04-13 |
| Zustand over Redux | Lightweight, TypeScript-first, simple Tauri IPC integration | 2026-04-12 |
| `cpal` crate for audio | Cross-platform audio abstraction (CoreAudio/WASAPI/ALSA) | 2026-04-13 |
| `x11rb` for Linux capture | Pure Rust X11 bindings, no C dependencies | 2026-04-13 |
| Unsafe Send/Sync for cpal::Stream | Required for Tauri managed state; safe behind Mutex | 2026-04-13 |
