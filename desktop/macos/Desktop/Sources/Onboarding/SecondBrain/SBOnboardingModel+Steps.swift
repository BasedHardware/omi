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
      // Show the drag-to-grant helper card (drag the Omi icon into the FDA list),
      // matching Screen Recording's flow. Full Disk Access has no in-place toggle,
      // so the drag card is the fastest grant path (#9742). Both FDA entry points
      // (the permission step and the Files connector) route through here.
      Task { await PermissionDragGuidance.presentDragToGrantHelper() }
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
          // System audio needs a SEPARATE Core Audio tap consent (the "bypass the
          // private window picker … screen and audio" prompt) beyond the Screen
          // Recording TCC this step grants. Prime it here — in-context on this step,
          // and awaited BEFORE we advance — so the modal surfaces on the system-audio
          // step (not a later one) and the real capture path never re-prompts after
          // onboarding. Screen Recording (which the tap requires) is granted now.
          if key == "system_audio", #available(macOS 14.4, *) {
            _ = await SystemAudioCaptureService.primePermission()
            guard !Task.isCancelled else { return }
          }
          // Auto-advance once the grant lands — the user shouldn't have to click
          // Continue after granting. Brief pause so the ✓ is visible, then only
          // advance if they're still on this permission's step (a late poll for a
          // step already left must never yank the flow forward).
          try? await Task.sleep(nanoseconds: 600_000_000)
          guard !Task.isCancelled else { return }
          self.autoAdvanceIfCurrent(key)
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
    if isGranted(key) {
      setPermOn(key)
      // If the user lands on the system-audio step already holding Screen Recording,
      // prime the separate Core Audio tap consent here (in-context) so it isn't
      // deferred to the first capture after onboarding. precheck doesn't advance, so
      // fire-and-forget is fine — the modal shows while this step is on screen.
      if key == "system_audio", #available(macOS 14.4, *) {
        Task.detached { _ = await SystemAudioCaptureService.primePermission() }
      }
    }
  }

  /// Fire a single throwaway ScreenCaptureKit capture the first time Screen
  /// Recording is confirmed granted during onboarding, so macOS surfaces the
  /// "bypass the private window picker" consent here — while the user is already
  /// granting screen access — instead of mid-question during the live screen demo
  /// (the exact spot users hit it). See `ScreenCaptureService.primeCaptureConsent`.
  func primeScreenCaptureConsentIfNeeded() {
    guard !didPrimeScreenCapture else { return }
    didPrimeScreenCapture = true
    if #available(macOS 14.0, *) {
      Task.detached { await ScreenCaptureService.primeCaptureConsent() }
    }
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
    case "system_audio":
      sysState = .on
      // System audio shares Screen Recording TCC; once it's on, the ScreenCaptureKit
      // capture consent can be primed so the demo doesn't surface it later.
      primeScreenCaptureConsentIfNeeded()
    case "screen_recording":
      scrState = .on
      primeScreenCaptureConsentIfNeeded()
    case "full_disk_access":
      fdaState = .on
      // The Files connector row shares the FDA grant; reflect it here so the row
      // flips to "on" when FDA is granted from the context step — its poll only
      // drives fdaState, unlike every other connector that writes back its own state.
      contextStates["files"] = "on"
      // Apple Notes reads through the same FDA grant, so re-probe it here too —
      // otherwise granting FDA leaves Notes showing a pointless "Connect" button.
      if contextStates["applenotes"] != "on" {
        Task { [weak self] in
          if await AppleNotesReaderService.shared.connectionStatus().isConnected {
            self?.contextStates["applenotes"] = "on"
          }
        }
      }
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

  /// Advance past a permission step automatically once its grant lands — but only
  /// when the user is still ON that step, so a late poll never skips a step they've
  /// already moved past.
  func autoAdvanceIfCurrent(_ key: String) {
    guard permissionKey(for: step) == key, permState(key) == .on else { return }
    switch step {
    case .mic: answerMic()
    case .systemAudio: answerSystemAudio()
    case .screen: answerScreen()
    case .files: answerFiles()
    case .accessibility: answerAccessibility()
    case .automation: answerAutomation()
    default: break
    }
  }

  /// The permission key a step gates on, or nil for non-permission steps.
  func permissionKey(for step: Step) -> String? {
    switch step {
    case .mic: return "microphone"
    case .systemAudio: return "system_audio"
    case .screen: return "screen_recording"
    case .files: return "full_disk_access"
    case .accessibility: return "accessibility"
    case .automation: return "automation"
    default: return nil
    }
  }

  /// Starting at `target`, skip past any permission step whose permission is
  /// already granted — so the user is never asked for something they've already
  /// given (matches the legacy onboarding's live permission detection). Refreshes
  /// each permission's TCC state before deciding, and reflects the grant so the
  /// row is already ✓ if we ever land on it. Returns the first step to actually ask.
  func firstUnaskedStep(from target: Step) -> Step {
    var step = target
    while let key = permissionKey(for: step) {
      refreshPermCheck(key)
      guard isGranted(key), let next = Step(rawValue: step.rawValue + 1) else { break }
      setPermOn(key)
      step = next
    }
    return step
  }
}

// MARK: - Summon shortcut (pick → press → notch)

extension SBOnboardingModel {
  /// Open-Omi options (tap to open the window).
  var openShortcutOptions: [(id: String, shortcut: ShortcutSettings.KeyboardShortcut, sub: String)] {
    [
      // ⌘O is registered as its own always-on Carbon hotkey (GlobalShortcutManager
      // .registerCommandO), so it reliably summons Omi globally — the natural,
      // expected "open" chord. Offer it first. (⌘J was dropped: onboarding testers
      // read it as arbitrary/random with no mnemonic, unlike ⌘O = "open".)
      ("cmdO", ShortcutSettings.askOmiCommandOShortcut, "tap to open"),
      ("cmdReturn", ShortcutSettings.askOmiCommandReturnShortcut, "tap to open"),
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
    if let l = NSEvent.addLocalMonitorForEvents(
      matching: mask,
      handler: { [weak self] event in
        let matched = self?.handleShortcutEvent(event) ?? false
        return matched ? nil : event
      })
    {
      shortcutMonitors.append(l)
    }
    if let g = NSEvent.addGlobalMonitorForEvents(
      matching: mask,
      handler: { [weak self] event in
        _ = self?.handleShortcutEvent(event)
      })
    {
      shortcutMonitors.append(g)
    }
  }

  /// The shortcuts offered on the current step — used so the user can just PRESS
  /// any offered combo to auto-select it (no need to click the row first).
  private var currentShortcutCandidates: [ShortcutSettings.KeyboardShortcut] {
    switch step {
    case .shortcutOpen: return openShortcutOptions.map { $0.shortcut }
    case .shortcutTalk: return talkShortcutOptions.map { $0.shortcut }
    default: return []
    }
  }

  private func handleShortcutEvent(_ event: NSEvent) -> Bool {
    guard !shortcutPressed else { return false }
    // If the user already tapped a row, honor that exact pick; otherwise let ANY
    // offered combo select itself on press, so "just press the key" works and the
    // Continue button appears without a separate pick-then-test step.
    let candidates = chosenShortcut.map { [$0] } ?? currentShortcutCandidates
    let isTalk = step == .shortcutTalk
    for sc in candidates {
      let matched: Bool
      switch event.type {
      case .flagsChanged: matched = sc.matchesFlagsChanged(event)  // modifier-only chords (fn, ⌥…)
      case .keyDown: matched = !event.isARepeat && sc.matchesKeyDown(event)  // ⌘O / ⌘↩ / ⌘J
      default: matched = false
      }
      if matched {
        DispatchQueue.main.async { [weak self] in
          guard let self else { return }
          if self.chosenShortcut != sc { self.pickShortcut(sc, isTalk: isTalk) }
          self.shortcutPressed = true
        }
        return true
      }
    }
    return false
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
    screenDemoDone = false
    FloatingControlBarManager.shared.setup(appState: appState, chatProvider: chatProvider)
    FloatingControlBarManager.shared.barState?.switchAIDraft(to: .onboardingFloating)
    resetFloatingBarConversation()
    if let bar = FloatingControlBarManager.shared.barState {
      PushToTalkManager.shared.setup(barState: bar)
      // Mark the demo done the first time Omi actually answers, so the Continue
      // button appears once the user has seen it work. The demo forces push-to-talk
      // (`pttTranscriptionModeDemoOverride = .live`), and a *voice* answer surfaces
      // through `voiceProjection` (the notch response phase) — it never flips
      // `showingAIResponse`, which is only set by the typed/`.mainResponse` path.
      // Watching only `showingAIResponse` is why the demo never advanced. Observe
      // BOTH signals so either a voice or a typed answer reveals Continue.
      // `resetFloatingBarConversation()` above cleared `showingAIResponse`, so its
      // subscribe-time value is already false. `voiceProjection` has no such reset,
      // and @Published replays its CURRENT value on subscribe — so on a resume/
      // re-entry of the demo a stale `isResponseActive` would fire immediately and
      // reveal Continue before the user does anything. `dropFirst()` ignores that
      // replayed value; a real answer is always a later emission.
      voiceCancellable = Publishers.Merge(
        bar.$showingAIResponse.filter { $0 }.map { _ in () },
        bar.$voiceProjection.dropFirst().filter { $0.isResponseActive }.map { _ in () }
      )
      .receive(on: DispatchQueue.main)
      .sink { [weak self] _ in self?.screenDemoDone = true }
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
    screenDemoDone = false
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

  /// Brand mark for a connector row (agents + context), so every row shows its
  /// real logo even when the app isn't installed (#10210). Brands without a
  /// bundled logo (openclaw/hermes/files) fall back to the icon's default glyph.
  func connectorBrand(_ id: String) -> ConnectorBrand {
    switch id {
    case "openclaw": return .openclaw
    case "hermes": return .hermes
    case "claudeCode": return .claudeCode
    case "codex": return .codex
    case "calendar": return .calendar
    case "gmail": return .gmail
    case "applenotes": return .appleNotes
    case "files": return .localFiles
    case "chatgpt": return .chatgpt
    case "claude": return .claude
    default: return .agents
    }
  }

  func refreshAgentStates() {
    // Show a "checking" placeholder up front so a not-installed agent never briefly
    // offers a "Connect" button that only flips to "not installed" after a click
    // (the async install probe below resolves each row to its real state).
    for row in agentRows where agentStates[row.id] == nil {
      agentStates[row.id] = "checking"
    }
    Task { [weak self] in
      guard let self else { return }
      for row in self.agentRows {
        // Only offer Connect for agents actually present on this Mac; otherwise
        // mark "unavailable" so the row shows "not installed" with no button.
        let installed = await Self.agentInstalled(self.agentDestination(row.id))
        guard installed else {
          self.agentStates[row.id] = "unavailable"
          continue
        }
        let connected = await MemoryExportService.shared.status(for: self.agentDestination(row.id)).hasConnection
        self.agentStates[row.id] = connected ? "on" : "idle"
      }
    }
  }

  /// Local install probe using the SAME evidence the real connect path requires,
  /// so a row never offers "Connect" and then flips to "not installed" on click
  /// (e.g. Codex: a stray `~/.codex` dir is not enough — the connector needs the
  /// `codex` binary on PATH). Delegates to `MemoryBankConnector.isInstalled`.
  private static func agentInstalled(_ destination: MemoryExportDestination) async -> Bool {
    await Task.detached { MemoryBankConnector.isInstalled(destination) }.value
  }

  func connectAgent(_ id: String) {
    guard agentStates[id] != "connecting", agentStates[id] != "checking", agentStates[id] != "on" else { return }
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
        // OAuth for these completes in the browser, so only the backend grant
        // list knows the truth — a local status check would never flip the chip.
        let connected = await MemoryExportService.shared.refreshCloudGrantConnectionStatus(for: dest).hasConnection
        if let resolved = Self.cloudContextState(current: self.contextStates[id], connected: connected) {
          self.contextStates[id] = resolved
        }
      }
      // Apple Notes rides the same Full Disk Access grant that powers Files, so a
      // readable NoteStore should show "✓ on" up front — not a "Connect" button
      // that would only flip to on for nothing (this precheck was missing, which
      // made the row look fake).
      if self.contextStates["applenotes"] != "on",
        await AppleNotesReaderService.shared.connectionStatus().isConnected
      {
        self.contextStates["applenotes"] = "on"
      }
      let cal = await CalendarReaderService.shared.verifyConnection()
      if cal.isConnected { self.contextStates["calendar"] = "on" }
      let gmail = await GmailReaderService.shared.verifyConnection()
      if gmail.isConnected { self.contextStates["gmail"] = "on" }
    }
  }

  /// Chip state for a cloud OAuth connector (ChatGPT/Claude) after a backend
  /// grant refresh: connected always wins; an unfinished "connecting" (the user
  /// came back without completing OAuth) resolves to "idle" so the Connect
  /// button returns; anything else is left unchanged (nil).
  nonisolated static func cloudContextState(current: String?, connected: Bool) -> String? {
    if connected { return "on" }
    return current == "connecting" ? "idle" : nil
  }

  /// Resolve a cookie-based Google connector (Calendar, Gmail). These don't OAuth —
  /// they read your existing browser Google session — so a "not signed in" result
  /// isn't an error to shrug at: OPEN the Google page so the user can actually sign
  /// in, then Retry picks up the new session. (An `.error`, e.g. a not-yet-loaded
  /// API key, just leaves a Retry button — opening Google wouldn't help.)
  private func resolveGoogleConnect(_ id: String, connected: Bool, needsSignIn: Bool, signInURL: String) {
    if connected {
      contextStates[id] = "on"
      return
    }
    contextStates[id] = "needsSignIn"
    if needsSignIn, let url = URL(string: signInURL) { NSWorkspace.shared.open(url) }
  }

  func connectContext(_ id: String) {
    guard contextStates[id] != "connecting", contextStates[id] != "on" else { return }
    contextStates[id] = "connecting"
    switch id {
    case "calendar":
      Task { [weak self] in
        let s = await CalendarReaderService.shared.verifyConnection()
        let needsSignIn = { if case .needsSignIn = s { return true } else { return false } }()
        self?.resolveGoogleConnect(
          "calendar", connected: s.isConnected, needsSignIn: needsSignIn, signInURL: "https://calendar.google.com")
      }
    case "gmail":
      Task { [weak self] in
        let s = await GmailReaderService.shared.verifyConnection()
        let needsSignIn = { if case .needsSignIn = s { return true } else { return false } }()
        self?.resolveGoogleConnect(
          "gmail", connected: s.isConnected, needsSignIn: needsSignIn, signInURL: "https://mail.google.com")
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
        let outcome: MemoryExportExecutor.Outcome
        do {
          outcome = try await MemoryExportExecutor.run(dest)
        } catch {
          self?.contextStates[id] = "unavailable"
          return
        }
        // Assisted/directory flows finish in the browser — checking now would
        // always read "not connected" and reset the chip. Keep it "connecting";
        // the app-activation refresh resolves it when the user comes back.
        guard outcome.mode == .completed else { return }
        let connected = await MemoryExportService.shared.status(for: dest).hasConnection
        self?.contextStates[id] = connected ? "on" : "idle"
      }
    default: break
    }
  }

  func answerContext() { advance(userAnswer: "Continue", to: .capture) }
}
