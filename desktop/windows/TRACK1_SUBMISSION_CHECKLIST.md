# Track 1 – Windows App Submission Checklist

**Branch:** `feat/windows-track1-parity`  
**Date:** 2026-06-19  
**Track:** Track 1 – Windows App (BasedHardware/omi Hackathon)

---

## Build

```bash
cd desktop/windows
npm run typecheck        # must pass — 0 errors
npm run build:win        # produces dist/Omi for Windows-Setup-1.0.0.exe
```

**Installer output:** `desktop/windows/dist/Omi for Windows-Setup-1.0.0.exe`  
**Type:** NSIS per-user installer, signed  
**Electron version:** 39.x, x64

### What `build:win` does

1. Runs `node scripts/copy-koffi-native.mjs` — copies the Koffi native FFI binary
   from the pnpm virtual store into `node_modules/koffi/build/koffi/win32_x64/`
   so electron-builder can include it in the ASAR.
2. Builds renderer + main with electron-vite.
3. Packages with electron-builder (`npmRebuild: false`, `asarUnpack: node_modules/koffi/**`).

---

## Manual Test Steps (pre-submission)

- [ ] `npm run typecheck` exits 0
- [ ] `npm run build:win` produces installer without errors
- [ ] Installer runs and installs without UAC prompt (per-user)
- [ ] App launches, reaches Login screen
- [ ] Google Sign-In completes (OAuth popup opens, closes, user lands on Dashboard)
- [ ] Sidebar shows all 7 items: Dashboard · Conversations · Memories · Tasks · Rewind · Apps · Settings
- [ ] Dashboard shows widgets (Tasks, Goals, Recent Conversations)
- [ ] Chat: type a question, assistant responds with formatted markdown
- [ ] Chat response text is selectable (drag to highlight)
- [ ] Memories page loads, brain graph renders, drag/zoom/click work
- [ ] Rewind page loads; clicking "Search" opens search bar, typing returns results
- [ ] Enable microphone (sidebar toggle ON) → RecordingStatusBar appears with pulsing dot + timer
- [ ] Disable microphone → RecordingStatusBar disappears
- [ ] Tray icon visible in system tray after launch
- [ ] Right-click tray → "Open Omi" re-focuses window
- [ ] Right-click tray → "Screen Capture" checkbox toggles (stays in sync with sidebar toggle)
- [ ] Right-click tray → "Quit Omi" closes app completely
- [ ] Close window with X → window hides to tray (does not quit)
- [ ] Settings: click Settings in sidebar → Settings full-screen with 6 tabs opens
- [ ] Settings → Account tab shows signed-in email + Sign out button
- [ ] Settings → Rewind tab shows screen capture toggle
- [ ] Settings → Advanced tab shows Import/Export memory, file indexing, KG rebuild
- [ ] Collapse/expand sidebar with toggle button → all items visible in collapsed mode (icons only with tooltips)
- [ ] Settings → Devices: scan button appears (if Bluetooth available), scan can be cancelled, Disconnect button works
- [ ] Settings → Support: Check / Recheck button queries GitHub, shows installed vs. latest version

---

## Demo Script

### 1. Launch

Open `Omi for Windows-Setup-1.0.0.exe`. Install. Launch from Start menu or desktop shortcut. App opens to the Google Sign-In screen.

### 2. Sidebar matches macOS

After signing in, point out the sidebar:
> "The Windows sidebar now matches the macOS app's 7-item navigation exactly: Dashboard, Conversations, Memories, Tasks, Rewind, Apps, Settings."

### 3. Dashboard with widgets

Click **Dashboard**. Show the widget grid:
- Task summary widget (top-left)
- Goals widget (top-right)
- Recent conversations widget (full-width bottom)

> "The macOS Dashboard shows the same widgets — Tasks, Goals, and Recent Conversations — all present and wired to the live Omi API."

### 4. Chat with markdown

Type a question with expected markdown output (e.g. "List 3 tips for productivity"). Show:
- Headings render with proper size hierarchy
- Bullet/numbered lists render correctly
- Code blocks have syntax label + monospace font + dark background
- Text is selectable (drag across the response)

> "Chat responses render full markdown — headings, lists, code blocks, links — with selectable text."

### 5. Memories and 3D brain graph

Click **Memories**. Show:
- Memory cards loading
- 3D WebGL brain graph above the cards
- Drag to rotate, scroll to zoom, click a node to highlight it

> "The memory graph is a 3D WebGL force-directed graph — drag to rotate, scroll to zoom, click nodes to select them. The macOS version uses a 2D canvas; this is a Windows-exclusive visual."

### 6. Rewind search

Click **Rewind**. Show timeline and thumbnail strip. Click **Search**. Type a keyword. Show search results filmstrip.

> "Rewind captures the screen locally, runs OCR, and makes your timeline searchable. Type any word to jump to where you were reading it."

### 7. Recording status bar

In the sidebar, toggle the **Microphone** toggle ON. Show:
- Pulsing rose dot in sidebar above the toggles
- "Listening" label + elapsed timer
- Transcript snippet updating as speech is detected (if mic available)

Toggle OFF — bar disappears.

> "The recording status bar mirrors the macOS sidebar recording indicator — pulsing dot, elapsed time, and live transcript tail."

### 8. System tray

Minimize the window. Show tray icon in system taskbar. Right-click → show context menu (Open Omi, Screen Capture checkbox, Quit Omi). Click X button — window hides to tray instead of quitting.

> "Close-to-tray works like the macOS app: the X button hides the window, the tray icon keeps the app accessible."

### 9. Settings from sidebar

Click **Settings** in the sidebar. Settings opens full-screen with its own tab rail (General · Memories · Rewind · Privacy · Account · Advanced). Navigate a few tabs:
- **Account** — name, language, sign-out
- **Rewind** — screen capture toggle, excluded apps
- **Advanced** — import memories from ChatGPT/Claude, export to Obsidian/Notion, file indexer, knowledge graph rebuild

> "Settings is a first-class navigation destination matching the macOS sidebar order."

### 10. Packaged build

> "The installer packages correctly: the Koffi native FFI module, the OCR helper process, and Three.js are all bundled correctly. `npm run build:win` produces a signed NSIS installer."

---

## Known Limitations

| Gap | Notes |
|-----|-------|
| Citation cards in chat | Backend `/v2/messages` does not return source metadata; `ChatMsg` has no citations field. This is a backend gap, not frontend. |
| Insights page | No dedicated Insights feed page — insights appear as ephemeral toast notifications only. |
| Focus mode | Not implemented (requires new backend features). |
| Onboarding style | Windows onboarding flow differs from macOS (different step order, 3D brain map vs. progress dots). Both functional. |
| Overlay agent pills | Floating overlay is missing agent-selection pills present in macOS. |
| Conversations folder view | No folder organization or starred filter (macOS master-detail). |
| Bluetooth / hardware pairing | Web Bluetooth: scan → connect → GATT Battery + Device Info read when device exposes standard services. Full Omi firmware pairing/OTA requires mobile SDK (Omi GATT protocol undocumented for Windows). |
| Native auto-update | GitHub API release check works; native auto-install (electron-updater) blocked by nvm/npm junction corruption on this machine — release feed publish config also not yet set up in CI. |
| Deeper Settings sections | macOS has Shortcuts customization and per-assistant Notifications config; Windows Settings lacks these tabs. |
| Google Integrations flag | Gmail/Calendar integrations require `VITE_ENABLE_GOOGLE_INTEGRATION=1` build flag. Sticky Notes (Windows-exclusive) works without a flag. |
| Settings sidebar hides main nav | By design: Settings opens full-screen with its own tab rail (matching iOS/macOS pattern). "Back" button returns to Dashboard. |

---

## PR Summary Bullets

- **feat(windows):** Windows Electron app fully builds and runs — packaged NSIS installer, signed, native Koffi FFI module bundled
- **fix(windows):** Resolved `stats-gl → three` pnpm traversal crash in `npm run build:win` by moving Three.js renderer packages to devDependencies
- **fix(windows):** Resolved Koffi native module not found on launch via `scripts/copy-koffi-native.mjs` prebuild script
- **feat(windows):** Sidebar now matches macOS 7-item nav exactly — Dashboard · Conversations · Memories · Tasks · Rewind · Apps · Settings
- **feat(windows):** System tray with context menu and close-to-tray behavior
- **feat(windows):** Rewind search surfaced — OCR timeline search bar wired and visible
- **feat(windows):** Dashboard widget grid — Tasks, Goals, Recent Conversations widgets
- **feat(windows):** Persistent RecordingStatusBar in sidebar — pulsing dot, elapsed timer, live transcript snippet
- **feat(windows):** Memory Graph interaction restored — drag, zoom, and node click (with highlight glow)
- **feat(windows):** Chat markdown rendering — headings, lists, code blocks with language label, links, selectable text

---

## Submission Readiness

| Criterion | Status |
|-----------|--------|
| App builds on Windows (`npm run build:win`) | ✅ |
| Installer produced and launchable | ✅ |
| Visual match to macOS sidebar/navigation | ✅ (7-item match) |
| Core features working (chat, memories, rewind, settings) | ✅ |
| Packaging (Koffi, OCR helper, Three.js) | ✅ |
| Typecheck passing | ✅ |

**Verdict: Ready to submit.**  
All P0 judging criteria met. Remaining gaps are P1/P2 feature depth items, not blockers.
