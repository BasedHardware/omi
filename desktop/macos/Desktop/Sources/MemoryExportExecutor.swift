import AppKit
import ApplicationServices
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
    let key = try await MemoryExportService.shared.ensureMCPKey()

    // OpenClaw / Hermes have no setup CLI; the agent doesn't reliably perform the
    // file write. Do it deterministically ourselves (idempotent local write).
    if MemoryBankConnector.handles(destination) {
      let message = try MemoryBankConnector.connect(destination, key: key)
      return Outcome(taskTitle: message, mode: .completed)
    }

    switch destination.mcpExecuteKind {
    case .localAutonomous:
      guard let task = destination.omiExecutionTask(key: key) else {
        throw ExecutorError.unsupported(destination.title)
      }
      await spawnSetupAgent(task: task)
      return Outcome(taskTitle: task.title, mode: .autonomous)

    case .browserAutonomous:
      return try await runBrowserAutonomous(destination, key: key)

    case .assisted:
      guard let task = destination.omiExecutionTask(key: key) else {
        throw ExecutorError.unsupported(destination.title)
      }
      await runAssisted(destination, key: key)
      return Outcome(taskTitle: task.title, mode: .assisted)
    }
  }

  private static func runBrowserAutonomous(
    _ destination: MemoryExportDestination,
    key: String
  ) async throws -> Outcome {
    guard let setup = destination.mcpSetup(key: key), let openURL = setup.openURL else {
      throw ExecutorError.unsupported(destination.title)
    }

    if destination == .claude {
      return try await runClaudeNativeCloudSetup(setup: setup, openURL: openURL, key: key)
    }

    let browser = BrowserAutomationTargetResolver.defaultTarget(for: openURL)
    let browserName = browser?.name ?? "your default browser"

    guard let task = destination.guidedBrowserSetupTask(key: key, browserName: browserName) else {
      throw ExecutorError.unsupported(destination.title)
    }

    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(
      "Server URL: \(setup.serverURL)\nKey: \(key)", forType: .string)

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
    openURL: URL,
    key: String
  ) async throws -> Outcome {
    CloudConnectorFormAutomation.dismissGuidanceOverlay()

    let args: [String: Any] = [
      "provider": "claude",
      "name": "Omi Memory",
      "server_url": setup.serverURL,
      "oauth_client_id": "omi",
      "oauth_client_secret": key,
      "submit": true,
    ]

    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(
      "Name: Omi Memory\nRemote MCP server URL: \(setup.serverURL)\nOAuth Client ID: omi\nOAuth Client Secret: \(key)",
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
      log("Claude cloud setup: native automation attempt \(attempt) result=\(cloudFormFillResultSummary(lastResult))")
      if cloudFormFillSucceeded(lastResult) {
        CloudConnectorFormAutomation.dismissGuidanceOverlay()
        return Outcome(
          taskTitle: "Claude connector form submitted. If Claude shows a final consent prompt, approve Omi Memory.",
          mode: .completed)
      }
      if cloudFormFillRequiresAccessibilityApproval(lastResult) {
        requestAccessibilityApprovalForCloudSetup()
        throw ExecutorError.browserSetupRequired(cloudSetupAccessibilityPermissionMessage)
      }
      if cloudFormFillRequiresScreenRecordingApproval(lastResult) {
        if lastResult.contains("hidden Add button"),
          CloudConnectorFormAutomation.showClaudeAddGuidanceOverlay()
        {
          throw ExecutorError.browserSetupRequired(cloudSetupManualClaudeAddMessage)
        } else if CloudConnectorFormAutomation.showClaudeConnectGuidanceOverlay() {
          throw ExecutorError.browserSetupRequired(cloudSetupManualClaudeConnectMessage)
        } else {
          requestScreenRecordingApprovalForCloudSetup()
          throw ExecutorError.browserSetupRequired(cloudSetupScreenRecordingPermissionMessage)
        }
      }
      if !cloudFormFillShouldRetry(lastResult) {
        break
      }
    }

    log("Claude cloud setup: stopping without agent fallback result=\(cloudFormFillResultSummary(lastResult))")
    throw ExecutorError.browserSetupRequired(cloudSetupNativeAutomationBlockedMessage(lastResult))
  }

  nonisolated static func cloudFormFillSucceeded(_ result: String) -> Bool {
    let cleanResult = !result.contains("Missing:")
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
    let sanitized = result
      .split(separator: "\n")
      .filter { !$0.lowercased().contains("oauth client secret") }
      .joined(separator: " | ")
    return String(sanitized.prefix(500))
  }

  private static func cloudSetupNativeAutomationBlockedMessage(_ result: String) -> String {
    """
    Omi opened Claude in your default browser and tried the native setup path first, but stopped before using the generic browser agent.

    Native setup result:
    \(cloudFormFillResultSummary(result))

    I did not start the Playwright/browser-agent fallback because Claude setup should stay in your signed-in default browser. If this looks like a permissions issue, approve the requested macOS permission and click "Do it for me" again.
    """
  }

  private static var cloudSetupAccessibilityPermissionMessage: String {
    """
    Omi needs Accessibility permission to finish Claude setup automatically.

    I opened Claude in your default browser and copied the connector values. Approve Accessibility for this Omi app in System Settings, then click "Do it for me" again.
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
    let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
    let trusted = AXIsProcessTrustedWithOptions(options)
    guard !trusted,
      let url = URL(
        string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
    else { return }
    NSWorkspace.shared.open(url)
  }

  private static func requestScreenRecordingApprovalForCloudSetup() {
    guard let url = URL(
      string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture")
    else { return }
    NSWorkspace.shared.open(url)
  }

  private static func runAssisted(_ destination: MemoryExportDestination, key: String) async {
    NSPasteboard.general.clearContents()
    NSPasteboard.general.setString(key, forType: .string)
    if let url = destination.mcpSetup(key: key)?.openURL {
      NSWorkspace.shared.open(url)
    }
    _ = await TasksStore.shared.createTask(
      description: "Finish connecting \(destination.title) to Omi (page opened, key copied)",
      dueAt: Date(), priority: "medium", tags: ["mcp-setup"])
  }

  private static func spawnSetupAgent(task: (title: String, body: String)) async {
    _ = await TasksStore.shared.createTask(
      description: task.title, dueAt: Date(), priority: "high", tags: ["mcp-setup"])
    let model =
      ShortcutSettings.shared.selectedModel.isEmpty
      ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
    let query = ProactiveTaskExecute.buildQuery(title: task.title, message: task.body)
    _ = AgentPillsManager.shared.spawn(
      query: query, model: model, systemPromptSuffix: ProactiveTaskExecute.systemPromptSuffix)
  }
}

private extension UserDefaults {
  func string(forKey key: String, fallback: String) -> String {
    string(forKey: key) ?? fallback
  }
}
