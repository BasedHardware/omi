import AppKit
import Foundation

/// Shared "Execute" logic for connector setup. Used by both the Execute button in
/// the connector sheet AND the automation bridge (`POST /execute-export`) so
/// headless e2e runs drive the exact same path — no separate execution flow.
///
/// Two modes (see `MemoryExportDestination.mcpExecuteKind`):
/// - `.autonomous` (Codex, Claude Code): spawn the agent to run a deterministic
///   CLI step end-to-end via the standard flow (TasksStore + AgentPillsManager).
/// - `.assisted` (ChatGPT, Claude): deterministically open the connector page and
///   copy the key, then track a finish-up task. Fully autonomous browser
///   navigation of those UIs isn't reliable enough to promise to every user.
@MainActor
enum MemoryExportExecutor {
  enum Mode: Sendable { case autonomous, assisted }
  struct Outcome: Sendable {
    let taskTitle: String
    let mode: Mode
  }

  enum ExecutorError: LocalizedError {
    case unsupported(String)
    var errorDescription: String? {
      switch self {
      case .unsupported(let name): return "\(name) does not support an MCP execution task."
      }
    }
  }

  static func run(_ destination: MemoryExportDestination) async throws -> Outcome {
    let key = try await MemoryExportService.shared.ensureMCPKey()
    guard let task = destination.omiExecutionTask(key: key) else {
      throw ExecutorError.unsupported(destination.title)
    }

    switch destination.mcpExecuteKind {
    case .autonomous:
      _ = await TasksStore.shared.createTask(
        description: task.title, dueAt: Date(), priority: "high", tags: ["mcp-setup"])
      let model =
        ShortcutSettings.shared.selectedModel.isEmpty
        ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
      let query = ProactiveTaskExecute.buildQuery(title: task.title, message: task.body)
      _ = AgentPillsManager.shared.spawn(
        query: query, model: model, systemPromptSuffix: ProactiveTaskExecute.systemPromptSuffix)
      return Outcome(taskTitle: task.title, mode: .autonomous)

    case .assisted:
      // Deterministic, reliable for everyone: copy the key and open the connector
      // page. The sheet's steps cover the final clicks.
      NSPasteboard.general.clearContents()
      NSPasteboard.general.setString(key, forType: .string)
      if let url = destination.mcpSetup(key: key)?.openURL {
        NSWorkspace.shared.open(url)
      }
      _ = await TasksStore.shared.createTask(
        description: "Finish connecting \(destination.title) to Omi (page opened, key copied)",
        dueAt: Date(), priority: "medium", tags: ["mcp-setup"])
      return Outcome(taskTitle: task.title, mode: .assisted)
    }
  }
}
