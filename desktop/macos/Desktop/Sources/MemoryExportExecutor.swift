import AppKit
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

    let browser =
      BrowserAutomationTargetResolver.target(for: BrowserAutomationTargetStore.selectedBundleIdentifier)
      ?? BrowserAutomationTargetResolver.defaultTarget(for: openURL)
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
