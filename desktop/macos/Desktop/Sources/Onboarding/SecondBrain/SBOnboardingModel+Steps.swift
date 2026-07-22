import AppKit
import Combine
import CoreGraphics
import Foundation

// MARK: - Permissions (one at a time)

extension SBOnboardingModel {
  func requestPerm(_ key: String) {
    switch key {
    case "microphone":
      micState = .waiting
      appState.requestMicrophonePermission()
      pollPermission(key)
    case "system_audio":
      // System-audio capture (Core Audio process tap) has no prompt of its own —
      // macOS gates it behind Screen Recording TCC. Requesting/reading screen
      // recording is the only thing that actually prompts + reliably detects.
      sysState = .waiting
      ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
      pollPermission(key)
    case "screen_recording":
      scrState = .waiting
      ScreenCaptureService.requestScreenRecordingAccessAndOpenSettings()
      pollPermission(key)
    case "full_disk_access":
      requestFullDiskAccess()
    case "accessibility":
      accState = .waiting
      appState.triggerAccessibilityPermission()
      pollPermission(key)
    case "automation":
      requestAutomation()
    default: break
    }
  }

  func requestFullDiskAccess() {
    fdaState = .waiting
    if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles") {
      NSWorkspace.shared.open(url)
    }
    pollPermission("full_disk_access")
  }

  /// Fire the Automation (Apple Events) TCC prompt by touching System Events,
  /// then poll for the grant. Mirrors the legacy request_permission=automation path.
  func requestAutomation() {
    autoState = .waiting
    // NSAppleScript is main-thread-only; running it off-main (the old bug) meant
    // the TCC prompt never fired. Launch System Events, then send a REAL Apple
    // Event (that send is what surfaces the Automation prompt), then detect
    // without re-prompting via checkAutomationPermission().
    Task { @MainActor [weak self] in
      guard let self else { return }
      NSAppleScript(source: "launch application \"System Events\"")?.executeAndReturnError(nil)
      try? await Task.sleep(nanoseconds: 1_000_000_000)
      var err: NSDictionary?
      NSAppleScript(
        source: "tell application \"System Events\" to return name of first process whose frontmost is true"
      )?.executeAndReturnError(&err)
      self.appState.checkAutomationPermission()
      self.pollPermission("automation")
    }
  }

  func pollPermission(_ key: String) {
    // Cancel only this key's prior poll — never a sibling permission's, so the
    // "both" mic+system-audio step can poll two grants at once.
    pollTasks[key]?.cancel()
    pollTasks[key] = Task { [weak self] in
      for _ in 0..<40 {  // ~20s
        try? await Task.sleep(nanoseconds: 500_000_000)
        guard let self, !Task.isCancelled else { return }
        self.refreshPermCheck(key)
        if self.isGranted(key) {
          self.setPermOn(key)
          return
        }
      }
      // Timed out without a grant. FDA/Accessibility routinely exceed 20s (open
      // System Settings → authenticate → toggle), so re-arm the Allow button
      // instead of stranding the row on "macOS…" forever.
      guard let self, !Task.isCancelled else { return }
      self.resetPermToAsk(key)
    }
  }

  /// Re-probe a single permission (each check writes the matching AppState flag).
  private func refreshPermCheck(_ key: String) {
    switch key {
    case "microphone": appState.checkMicrophonePermission()
    case "system_audio": appState.checkScreenRecordingPermission()  // shares Screen Recording TCC
    case "screen_recording": appState.checkScreenRecordingPermission()
    case "full_disk_access": appState.checkFullDiskAccess()
    case "accessibility": appState.checkAccessibilityPermission()
    case "automation": appState.checkAutomationPermission()
    default: appState.checkAllPermissions()
    }
  }

  /// When a permission step appears, reflect a grant the user already has so it
  /// shows ✓ instead of an Allow button they'd tap for nothing.
  func precheckPerm(_ key: String) {
    refreshPermCheck(key)
    if isGranted(key) { setPermOn(key) }
  }

  func isGranted(_ key: String) -> Bool {
    switch key {
    case "microphone": return appState.hasMicrophonePermission
    case "system_audio": return appState.hasScreenRecordingPermission  // shares Screen Recording TCC
    case "screen_recording": return appState.hasScreenRecordingPermission
    case "full_disk_access": return appState.hasFullDiskAccess
    case "accessibility": return appState.hasAccessibilityPermission && !appState.isAccessibilityBroken
    case "automation": return appState.hasAutomationPermission
    default: return false
    }
  }

  func setPermOn(_ key: String) {
    switch key {
    case "microphone": micState = .on
    case "system_audio": sysState = .on
    case "screen_recording": scrState = .on
    case "full_disk_access":
      fdaState = .on
      // The Files connector row shares the FDA grant; reflect it here so the row
      // flips to "on" when FDA is granted from the context step — its poll only
      // drives fdaState, unlike every other connector that writes back its own state.
      contextStates["files"] = "on"
    case "accessibility": accState = .on
    case "automation": autoState = .on
    default: break
    }
  }

  /// Return a still-`.waiting` row to `.ask` so its Allow button reappears after
  /// the poll times out without a grant (a later grant re-triggers the poll).
  func resetPermToAsk(_ key: String) {
    switch key {
    case "microphone": micState = .ask
    case "system_audio": sysState = .ask
    case "screen_recording": scrState = .ask
    case "full_disk_access": fdaState = .ask
    case "accessibility": accState = .ask
    case "automation": autoState = .ask
    default: break
    }
  }

  func permState(_ key: String) -> PermState {
    switch key {
    case "microphone": return micState
    case "system_audio": return sysState
    case "screen_recording": return scrState
    case "full_disk_access": return fdaState
    case "accessibility": return accState
    case "automation": return autoState
    default: return .ask
    }
  }

  func answerMic() { advance(userAnswer: micState == .on ? "Allowed" : "Skip", to: .systemAudio) }
  func answerSystemAudio() { advance(userAnswer: sysState == .on ? "Allowed" : "Skip", to: .screen) }
  func answerScreen() { advance(userAnswer: scrState == .on ? "Allowed" : "Skip", to: .files) }
  func answerFiles() { advance(userAnswer: fdaState == .on ? "Allowed" : "Skip", to: .accessibility) }
  func answerAccessibility() { advance(userAnswer: accState == .on ? "Allowed" : "Skip", to: .automation) }
  func answerAutomation() { advance(userAnswer: autoState == .on ? "Allowed" : "Skip", to: .shortcutOpen) }
}

// MARK: - Summon shortcut (pick → press → notch)

extension SBOnboardingModel {
  /// Open-Omi options (tap to open the window).
  var openShortcutOptions: [(id: String, shortcut: ShortcutSettings.KeyboardShortcut, sub: String)] {
    [
      ("cmdO", ShortcutSettings.askOmiCommandOShortcut, "tap to open"),
      ("cmdReturn", ShortcutSettings.askOmiCommandReturnShortcut, "tap to open"),
      ("cmdJ", ShortcutSettings.askOmiCommandJShortcut, "tap to open"),
    ]
  }

  /// Push-to-talk options (hold to talk, hands-free).
  var talkShortcutOptions: [(id: String, shortcut: ShortcutSettings.KeyboardShortcut, sub: String)] {
    [
      ("fn", ShortcutSettings.KeyboardShortcut(modifierOnly: .function), "hold to talk"),
      ("opt", ShortcutSettings.KeyboardShortcut(modifierOnly: .option), "hold to talk"),
      ("ctrl", ShortcutSettings.KeyboardShortcut(modifierOnly: .control), "hold to talk"),
    ]
  }

  /// Arm key detection exactly like the legacy OnboardingFloatingBarShortcutStepView:
  /// suspend the live Ask-Omi Carbon hotkey (so pressing it doesn't steal focus or
  /// get swallowed before our monitor sees it) and null the main menu (⌘O/⌘↩ are
  /// NSMenu key equivalents that AppKit dispatches before local monitors). Both are
  /// restored on leave. This is why the earlier attempt's monitor never fired.
  func armShortcutSummon() {
    // Reset pick/press state so each shortcut step (open, then talk) starts fresh.
    shortcutPicked = false
    shortcutPressed = false
    shortcutTokens = []
    chosenShortcut = nil
    GlobalShortcutManager.shared.setRegistrationSuspended(true)
    if savedMainMenu == nil { savedMainMenu = NSApp.mainMenu }
    NSApp.mainMenu = nil
    installShortcutMonitors()
  }

  func disarmShortcutSummon() {
    for m in shortcutMonitors { NSEvent.removeMonitor(m) }
    shortcutMonitors.removeAll()
    if let saved = savedMainMenu {
      NSApp.mainMenu = saved
      savedMainMenu = nil
    }
    GlobalShortcutManager.shared.setRegistrationSuspended(false)
  }

  private func installShortcutMonitors() {
    for m in shortcutMonitors { NSEvent.removeMonitor(m) }
    shortcutMonitors.removeAll()
    let mask: NSEvent.EventTypeMask = [.keyDown, .keyUp, .flagsChanged]
    // Local monitor fires when the app is key and can consume the event; global
    // monitor fires when another app is focused (it can only observe).
    if let l = NSEvent.addLocalMonitorForEvents(matching: mask, handler: { [weak self] event in
      let matched = self?.handleShortcutEvent(event) ?? false
      return matched ? nil : event
    }) {
      shortcutMonitors.append(l)
    }
    if let g = NSEvent.addGlobalMonitorForEvents(matching: mask, handler: { [weak self] event in
      _ = self?.handleShortcutEvent(event)
    }) {
      shortcutMonitors.append(g)
    }
  }

  private func handleShortcutEvent(_ event: NSEvent) -> Bool {
    guard !shortcutPressed, let sc = chosenShortcut else { return false }
    let matched: Bool
    switch event.type {
    case .flagsChanged: matched = sc.matchesFlagsChanged(event)  // modifier-only chords (fn, ⌥…)
    case .keyDown: matched = !event.isARepeat && sc.matchesKeyDown(event)  // ⌘O / ⌘↩ / ⌘J
    default: matched = false
    }
    if matched {
      DispatchQueue.main.async { [weak self] in self?.shortcutPressed = true }
    }
    return matched
  }

  /// Pick + persist a shortcut. `isTalk` → push-to-talk chord (held, drives the
  /// voice demo); otherwise the Ask-Omi open hotkey (tapped to open the window).
  func pickShortcut(_ shortcut: ShortcutSettings.KeyboardShortcut, isTalk: Bool) {
    chosenShortcut = shortcut
    chosenShortcutIsPTT = isTalk
    shortcutTokens = shortcut.displayTokens
    shortcutPicked = true
    shortcutPressed = false
    if isTalk {
      ShortcutSettings.shared.pttShortcut = shortcut
      ShortcutSettings.shared.pttEnabled = true
    } else {
      ShortcutSettings.shared.askOmiShortcut = shortcut
      ShortcutSettings.shared.askOmiEnabled = true
    }
  }

  func answerShortcutOpen() {
    advance(userAnswer: shortcutPressed ? "Works" : (shortcutPicked ? "Set" : "Skip"), to: .shortcutTalk)
  }
  func answerShortcutTalk() {
    advance(userAnswer: shortcutPressed ? "Works" : (shortcutPicked ? "Set" : "Skip"), to: .screenDemo)
  }
}

// MARK: - Screen + voice demo (live: notch visible, screen-aware answer)

extension SBOnboardingModel {
  /// Wire the real floating bar + push-to-talk exactly like the legacy
  /// OnboardingVoiceDemoView: isolate the demo conversation (onboardingFloating
  /// draft + the `.onboarding()` journal surface via `isOnboarding`), force live
  /// transcription, warm the bridge, and SHOW the notch so it stays visible while
  /// the user holds their key and asks about the screen. Screen capture is
  /// attached automatically for screen-aware questions; the answer streams into
  /// the notch, which spins while Omi is thinking.
  func startScreenDemo() {
    FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
    FloatingControlBarManager.shared.barState?.switchAIDraft(to: .onboardingFloating)
    resetFloatingBarConversation()
    if let bar = FloatingControlBarManager.shared.barState {
      PushToTalkManager.shared.setup(barState: bar)
    }
    ShortcutSettings.shared.pttTranscriptionModeDemoOverride = .live
    Task { await chatProvider.warmupBridge() }
    FloatingControlBarManager.shared.show()
  }

  private func resetFloatingBarConversation() {
    guard let bar = FloatingControlBarManager.shared.barState else { return }
    bar.showingAIConversation = false
    bar.showingAIResponse = false
    bar.aiInputText = ""
    bar.clearViewport()
  }

  func teardownVoiceDemo() {
    voiceTimeout?.cancel()
    voiceTimeout = nil
    voiceCancellable = nil
    ShortcutSettings.shared.pttTranscriptionModeDemoOverride = nil
    resetFloatingBarConversation()
    PushToTalkManager.shared.cleanup()
    FloatingControlBarManager.shared.hide()
  }

  /// The push-to-talk chord to prompt for the voice demo.
  var voiceChordTokens: [String] {
    let tokens = ShortcutSettings.shared.pttShortcut.displayTokens
    return tokens.isEmpty ? ["fn"] : tokens
  }

  func answerScreenDemo() { advance(userAnswer: "Continue", to: .agents) }
}

// MARK: - Agents (do things for you)

extension SBOnboardingModel {
  var agentRows: [(id: String, name: String, detail: String)] {
    [
      ("openclaw", "OpenClaw", "runs tasks on your Mac"),
      ("hermes", "Hermes", "autonomous background agent"),
      ("claudeCode", "Claude Code", "codes in your repos"),
      ("codex", "Codex", "OpenAI's coding agent"),
    ]
  }

  private func agentDestination(_ id: String) -> MemoryExportDestination {
    switch id {
    case "openclaw": return .openclaw
    case "hermes": return .hermes
    case "claudeCode": return .claudeCode
    case "codex": return .codex
    default: return .openclaw
    }
  }

  func refreshAgentStates() {
    Task { [weak self] in
      guard let self else { return }
      for row in self.agentRows {
        // Only offer Connect for agents actually present on this Mac; otherwise
        // mark "unavailable" so the row shows "not installed" with no button.
        let installed = await Self.agentInstalled(row.id)
        guard installed else {
          self.agentStates[row.id] = "unavailable"
          continue
        }
        let connected = await MemoryExportService.shared.status(for: self.agentDestination(row.id)).hasConnection
        self.agentStates[row.id] = connected ? "on" : "idle"
      }
    }
  }

  /// Best-effort local install probe: presence of the tool's config/home dir.
  private static func agentInstalled(_ id: String) async -> Bool {
    await Task.detached {
      let home = FileManager.default.homeDirectoryForCurrentUser
      let fm = FileManager.default
      func exists(_ rel: String) -> Bool { fm.fileExists(atPath: home.appendingPathComponent(rel).path) }
      switch id {
      case "openclaw": return exists(".openclaw")
      case "hermes": return exists(".hermes")
      case "claudeCode": return exists(".claude.json") || exists(".claude")
      case "codex": return exists(".codex")
      default: return false
      }
    }.value
  }

  func connectAgent(_ id: String) {
    guard agentStates[id] != "connecting", agentStates[id] != "on" else { return }
    agentStates[id] = "connecting"
    let dest = agentDestination(id)
    Task { [weak self] in
      do {
        _ = try await MemoryExportExecutor.run(dest)
      } catch {
        self?.agentStates[id] = "unavailable"
        return
      }
      guard let self else { return }
      let connected = await MemoryExportService.shared.status(for: dest).hasConnection
      self.agentStates[id] = connected ? "on" : "idle"
    }
  }

  func answerAgents() { advance(userAnswer: "Continue", to: .context) }
}

// MARK: - Context (connect what I can see)

extension SBOnboardingModel {
  var contextRows: [(id: String, name: String, detail: String)] {
    [
      ("calendar", "Calendar", "meetings + prep"),
      ("gmail", "Gmail", "email follow-ups"),
      ("applenotes", "Apple Notes", "your notes"),
      ("files", "Files", "docs on this Mac"),
      ("chatgpt", "ChatGPT", "carry memory across"),
      ("claude", "Claude", "carry memory across"),
    ]
  }

  func refreshContextStates() {
    if appState.hasFullDiskAccess { contextStates["files"] = "on" }
    Task { [weak self] in
      guard let self else { return }
      for id in ["chatgpt", "claude"] {
        let dest: MemoryExportDestination = id == "chatgpt" ? .chatgpt : .claude
        if await MemoryExportService.shared.status(for: dest).hasConnection { self.contextStates[id] = "on" }
      }
      let cal = await CalendarReaderService.shared.verifyConnection()
      if cal.isConnected { self.contextStates["calendar"] = "on" }
    }
  }

  func connectContext(_ id: String) {
    guard contextStates[id] != "connecting", contextStates[id] != "on" else { return }
    contextStates[id] = "connecting"
    switch id {
    case "calendar":
      Task { [weak self] in
        let s = await CalendarReaderService.shared.verifyConnection()
        self?.contextStates["calendar"] = s.isConnected ? "on" : "needsSignIn"
      }
    case "gmail":
      Task { [weak self] in
        let s = await GmailReaderService.shared.verifyConnection()
        self?.contextStates["gmail"] = s.isConnected ? "on" : "needsSignIn"
      }
    case "applenotes":
      Task { [weak self] in
        guard let self else { return }
        // Full Disk Access covers Notes when it applies; if not, grant a
        // security-scoped folder bookmark (the real, re-sign-proof connect path).
        var status = await AppleNotesReaderService.shared.connectionStatus()
        if status.isConnected {
          self.contextStates["applenotes"] = "on"
          return
        }
        let pickedPath: String? = await MainActor.run {
          let panel = NSOpenPanel()
          panel.canChooseDirectories = true
          panel.canChooseFiles = false
          panel.allowsMultipleSelection = false
          panel.prompt = "Grant access"
          panel.message = "Pick your Notes data folder so I can read it."
          panel.directoryURL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Group Containers/group.com.apple.notes")
          return panel.runModal() == .OK ? panel.url?.path : nil
        }
        guard let path = pickedPath else {
          self.contextStates["applenotes"] = "needsSignIn"
          return
        }
        do {
          _ = try await AppleNotesReaderService.shared.validateSelectedFolder(path: path)
          status = await AppleNotesReaderService.shared.connectionStatus(selectedFolderPath: path)
          self.contextStates["applenotes"] = status.isConnected ? "on" : "needsSignIn"
        } catch {
          self.contextStates["applenotes"] = "needsSignIn"
        }
      }
    case "files":
      appState.checkFullDiskAccess()
      if appState.hasFullDiskAccess {
        contextStates["files"] = "on"
      } else {
        requestFullDiskAccess()
        contextStates["files"] = "idle"
      }
    case "chatgpt", "claude":
      let dest: MemoryExportDestination = id == "chatgpt" ? .chatgpt : .claude
      Task { [weak self] in
        do {
          _ = try await MemoryExportExecutor.run(dest)
        } catch {
          self?.contextStates[id] = "unavailable"
          return
        }
        let connected = await MemoryExportService.shared.status(for: dest).hasConnection
        self?.contextStates[id] = connected ? "on" : "idle"
      }
    default: break
    }
  }

  func answerContext() { advance(userAnswer: "Continue", to: .capture) }
}
