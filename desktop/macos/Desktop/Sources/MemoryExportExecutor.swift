import AppKit
@preconcurrency import ApplicationServices
import Foundation

/// Shared "Execute" logic for connector setup. Used by both the Execute button in
/// the connector sheet AND the automation bridge (`POST /execute-export`) so
/// headless e2e runs drive the exact same path — no separate execution flow.
///
/// Execution modes are explicit because local CLI setup and cloud-browser setup
/// have very different preflight requirements.
@MainActor
enum MemoryExportExecutor {
  enum Mode: Sendable { case autonomous, assisted, completed }
  struct Outcome: Sendable {
    let taskTitle: String
    let mode: Mode
  }

  enum ExecutorError: LocalizedError {
    case unsupported(String)
    case browserSetupRequired(String)
    var errorDescription: String? {
      switch self {
      case .unsupported(let name): return "\(name) does not support an MCP execution task."
      case .browserSetupRequired(let message): return message
      }
    }
  }

  static func run(_ destination: MemoryExportDestination) async throws -> Outcome {
    if case .directoryApp = destination.mcpExecuteKind {
      guard let directoryURL = destination.directoryInstallURL else {
        throw ExecutorError.unsupported(destination.title)
      }
      NSWorkspace.shared.open(directoryURL)
      return Outcome(
        taskTitle: "Opened Omi in ChatGPT. Add Omi and authorize it there, then return to Omi.",
        mode: .assisted)
    }

    if requiresAccessibilityPreflight(destination), !isAccessibilityReadyForBrowserSetup() {
      requestAccessibilityApprovalForCloudSetup()
      throw ExecutorError.browserSetupRequired(cloudSetupAccessibilityPermissionMessage)
    }

    let key = try await hostedMCPKey(for: destination)

    if MemoryBankConnector.handles(destination) {
      if canSkipLocalSetupWhenConfigMatches(destination),
        MemoryExportConnectionDetector.hasExistingConnection(for: destination, matchingKey: key)
      {
        return Outcome(taskTitle: "\(destination.title) is already connected.", mode: .completed)
      }
      let message = try MemoryBankConnector.connect(destination, key: key)
      await MemoryExportService.shared.markConnected(destination)
      return Outcome(taskTitle: message, mode: .completed)
    }

    switch destination.mcpExecuteKind {
    case .directoryApp:
      throw ExecutorError.unsupported(destination.title)
    case .localAutonomous:
      guard let task = destination.omiExecutionTask(key: key) else {
        throw ExecutorError.unsupported(destination.title)
      }
      await spawnSetupAgent(task: task)
      return Outcome(taskTitle: task.title, mode: .autonomous)

    case .browserAutonomous:
      return try await runBrowserAutonomous(destination, key: key)

    case .assisted:
      guard destination.omiExecutionTask(key: key) != nil else {
        throw ExecutorError.unsupported(destination.title)
      }
      return await runAssisted(destination, key: key)
    }
  }

  private static func canSkipLocalSetupWhenConfigMatches(_ destination: MemoryExportDestination) -> Bool {
    switch destination {
    case .claudeCode, .codex:
      return true
    case .openclaw, .hermes:
      return false
    case .notion, .obsidian, .chatgpt, .claude, .gemini, .agents:
      return false
    }
  }

  private static func hostedMCPKey(for destination: MemoryExportDestination) async throws -> String {
    guard destination.requiresHostedMCPKeyForSetup else { return "" }
    if MemoryBankConnector.handles(destination) {
      return try await MemoryExportService.shared.mcpKeyForLocalConnectorSetup()
    }
    return try await MemoryExportService.shared.ensureMCPKey()
  }

  static func requiresAccessibilityPreflight(_ destination: MemoryExportDestination) -> Bool {
    destination == .claude && destination.mcpExecuteKind == .browserAutonomous
  }

  static func accessibilityPreflightMissing(for destination: MemoryExportDestination) -> Bool {
    requiresAccessibilityPreflight(destination) && !isAccessibilityReadyForBrowserSetup()
  }

  private static func isAccessibilityReadyForBrowserSetup() -> Bool {
    AXIsProcessTrusted()
  }

  /// PARKED: no destination currently maps to `.browserAutonomous` — ChatGPT and
  /// Claude cloud moved to the assisted flow because AX/OCR automation of other
  /// people's web UIs proved too brittle across browsers and machines. Kept so a
  /// future DOM-perception rebuild has the routing to slot into. Do not remap a
  /// destination here without reading docs/cloud-connectors-roadmap.md.
  private static func runBrowserAutonomous(
    _ destination: MemoryExportDestination,
    key: String
  ) async throws -> Outcome {
    guard let setup = destination.mcpSetup(key: key), let openURL = setup.openURL else {
      throw ExecutorError.unsupported(destination.title)
    }

    if destination == .claude {
      return try await runClaudeNativeCloudSetup(setup: setup, openURL: openURL)
    }

    let browser = BrowserAutomationTargetResolver.defaultTarget(for: openURL)
    let browserName = browser?.name ?? "your default browser"

    guard let task = destination.guidedBrowserSetupTask(key: key, browserName: browserName) else {
      throw ExecutorError.unsupported(destination.title)
    }

    let pasteboardText =
      destination.requiresHostedMCPKeyForSetup
      ? "Server URL: \(setup.serverURL)\nKey: \(key)"
      : "Server URL: \(setup.serverURL)"
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(pasteboardText, forType: .string)

    if let browser {
      BrowserAutomationTargetResolver.open(openURL, in: browser)
    } else {
      NSWorkspace.shared.open(openURL)
    }

    await spawnSetupAgent(task: task)
    return Outcome(taskTitle: task.title, mode: .autonomous)
  }

  private static func runClaudeNativeCloudSetup(
    setup: MCPSetup,
    openURL: URL
  ) async throws -> Outcome {
    CloudConnectorFormAutomation.dismissGuidanceOverlay()

    let args: [String: Any] = [
      "provider": "claude",
      "name": "Omi Memory",
      "server_url": setup.serverURL,
      "oauth_client_id": MemoryExportDestination.claude.cloudOAuthClientID ?? "",
      "submit": true,
    ]

    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(
      """
      Name: Omi Memory
      Remote MCP server URL: \(setup.serverURL)
      OAuth Client ID: \(MemoryExportDestination.claude.cloudOAuthClientID ?? "")
      OAuth Client Secret: leave blank
      """,
      forType: .string)

    // For cloud setup, use the user's system default browser. Do not reuse the
    // Playwright/extension browser preference: that can point at Chrome even
    // when the user is signed into Claude in Atlas/Arc/another default browser.
    log("Claude cloud setup: opening connector page in default browser for native automation")
    NSWorkspace.shared.open(openURL)

    var lastResult = ""
    for attempt in 1...12 {
      try? await Task.sleep(nanoseconds: attempt == 1 ? 1_500_000_000 : 750_000_000)
      lastResult = await CloudConnectorFormAutomation.fill(args)
      log(
        "Claude cloud setup: native automation attempt \(attempt) result=\(cloudFormFillResultSummary(lastResult))"
      )
      if cloudFormFillSucceeded(lastResult) {
        CloudConnectorFormAutomation.dismissGuidanceOverlay()
        if lastResult.contains("Claude connector connected.") {
          await MemoryExportService.shared.markConnected(.claude)
        }
        return Outcome(
          taskTitle:
            "Claude connector form submitted. If Claude shows a final consent prompt, approve Omi Memory.",
          mode: .completed)
      }
      if cloudFormFillRequiresAccessibilityApproval(lastResult) {
        requestAccessibilityApprovalForCloudSetup()
        throw ExecutorError.browserSetupRequired(cloudSetupAccessibilityPermissionMessage)
      }
      if cloudFormFillNeedsManualClaudeAdd(lastResult),
        CloudConnectorFormAutomation.showClaudeAddGuidanceOverlay()
      {
        throw ExecutorError.browserSetupRequired(cloudSetupManualClaudeAddMessage)
      }
      if cloudFormFillRequiresScreenRecordingApproval(lastResult) {
        if CloudConnectorFormAutomation.showClaudeConnectGuidanceOverlay() {
          throw ExecutorError.browserSetupRequired(cloudSetupManualClaudeConnectMessage)
        } else {
          // We could not anchor to Claude. Send the user to grant Screen Recording, but
          // never leave them on a bare settings pane: show an instruction card too.
          requestScreenRecordingApprovalForCloudSetup()
          await CloudConnectorFormAutomation.showScreenRecordingSettingsInstructionOverlay(
            actionLabel: "Connect")
          throw ExecutorError.browserSetupRequired(cloudSetupScreenRecordingPermissionMessage)
        }
      }
      if !cloudFormFillShouldRetry(lastResult) {
        break
      }
    }

    log(
      "Claude cloud setup: stopping without agent fallback result=\(cloudFormFillResultSummary(lastResult))"
    )
    throw ExecutorError.browserSetupRequired(cloudSetupNativeAutomationBlockedMessage)
  }

  nonisolated static func cloudFormFillSucceeded(_ result: String) -> Bool {
    let cleanResult =
      !result.contains("Missing:")
      && !result.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("Error:")
    return cleanResult
      && (result.contains("Submitted with button: Connect")
        || result.contains("Submitted with button: Create")
        || result.contains("Submitted with button: Save")
        || result.contains("Claude connector connected."))
  }

  static func cloudFormFillRequiresAccessibilityApproval(_ result: String) -> Bool {
    result.lowercased().contains("accessibility permission is not available")
  }

  static func cloudFormFillRequiresScreenRecordingApproval(_ result: String) -> Bool {
    result.lowercased().contains("screen recording permission is not available")
  }

  nonisolated static func cloudFormFillShouldRetry(_ result: String) -> Bool {
    result.contains("Could not find a visible")
      || result.contains("Submit skipped: no enabled")
      || result.contains("set failed")
      || result.contains("Submitted with button: Add")
  }

  private static func cloudFormFillResultSummary(_ result: String) -> String {
    let sanitized =
      result
      .split(separator: "\n")
      .filter { !$0.lowercased().contains("oauth client secret") }
      .joined(separator: " | ")
    return String(sanitized.prefix(500))
  }

  static func cloudFormFillNeedsManualClaudeAdd(_ result: String) -> Bool {
    let lower = result.lowercased()
    return lower.contains("hidden add button")
      || lower.contains("claude add connector button is not exposed")
      || (lower.contains("claude add") && lower.contains("not exposed to accessibility"))
      || (lower.contains("add connector button") && lower.contains("refusing blind"))
  }

  private static var cloudSetupNativeAutomationBlockedMessage: String {
    """
    Omi opened Claude in your default browser, but Claude still needs one manual step.

    Finish the connector setup in the Claude window that is already open. If the connector form is filled, click Add. If Claude asks for permission, approve Omi Memory.

    If nothing is waiting in Claude, click "Do it for me" again or use the manual installation steps below.
    """
  }

  private static var cloudSetupAccessibilityPermissionMessage: String {
    """
    Omi needs Accessibility permission to finish Claude setup automatically.

    Approve Accessibility for this Omi app in System Settings, then click "Do it for me" again. If you do not want to grant it, use the manual installation steps below.
    """
  }

  private static var cloudSetupScreenRecordingPermissionMessage: String {
    """
    Omi needs Screen Recording permission to finish Claude setup automatically.

    I added the Claude connector, but Claude hides the final Connect button from Accessibility in this browser. Approve Screen Recording for this Omi app in System Settings, then click "Do it for me" again.
    """
  }

  private static var cloudSetupManualClaudeConnectMessage: String {
    """
    Claude is waiting for one final click.

    I added the connector and pointed to the Connect button in your browser.
    """
  }

  private static var cloudSetupManualClaudeAddMessage: String {
    """
    Claude is waiting for one click.

    I filled the connector form and pointed to the Add button in your browser.
    """
  }

  private static func requestAccessibilityApprovalForCloudSetup() {
    let options =
      [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    let trusted = AXIsProcessTrustedWithOptions(options)
    guard !trusted,
      let url = URL(
        string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
    else { return }
    NSWorkspace.shared.open(url)
  }

  private static func requestScreenRecordingApprovalForCloudSetup() {
    // Actually request access first. CGRequestScreenCaptureAccess() both shows the
    // system consent prompt AND registers this app in the Screen Recording list with a
    // ready-to-flip toggle. Without it the app never appears in the list, so opening
    // Settings alone left the user with nothing to turn on.
    ScreenCaptureService.requestAllScreenCapturePermissions()

    guard
      let url = URL(
        string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
    else { return }
    NSWorkspace.shared.open(url)
  }

  /// Assisted setup: everything deterministic happens in code (copy the full
  /// field payload, open the deep link), then an on-screen card tells the user
  /// the one thing left to do. This is the primary path for ChatGPT/Claude cloud
  /// connectors — see docs/cloud-connectors-roadmap.md for why autonomous
  /// browser automation is parked and what replaces it.
  private static func runAssisted(_ destination: MemoryExportDestination, key: String) async -> Outcome {
    if let url = destination.mcpSetup(key: key)?.openURL {
      NSWorkspace.shared.open(url)
    }

    if let hint = destination.assistedOverlayHint,
      let sections = destination.assistedSetupSections(key: key)
    {
      CloudConnectorGuidanceOverlay.shared.presentFieldCopyCard(
        title: hint.title, subtitle: hint.subtitle, sections: sections, near: nil)
      return Outcome(
        taskTitle:
          "Opened \(destination.title) — copy each value from the on-screen card into the form.",
        mode: .assisted)
    }

    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(key, forType: .string)

    _ = await TasksStore.shared.createTask(
      description: "Finish connecting \(destination.title) to Omi (page opened, key copied)",
      dueAt: Date(), priority: "medium", tags: ["mcp-setup"])
    return Outcome(
      taskTitle: "Opened \(destination.title) and copied your key — finish with the steps below.",
      mode: .assisted)
  }

  private static func spawnSetupAgent(task: (title: String, body: String)) async {
    _ = await TasksStore.shared.createTask(
      description: task.title, dueAt: Date(), priority: "high", tags: ["mcp-setup"])
    let model =
      ShortcutSettings.shared.selectedModel.isEmpty
      ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
    let query = ProactiveTaskExecute.buildQuery(title: task.title, message: task.body)
    _ = AgentPillsManager.shared.spawn(
      query: query,
      model: model,
      originSurface: .mainChat,
      systemPromptSuffix: ProactiveTaskExecute.systemPromptSuffix)
  }
}
