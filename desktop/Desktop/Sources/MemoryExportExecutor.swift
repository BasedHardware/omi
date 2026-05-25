import Foundation

/// Shared "Execute" logic for connector setup: mint the MCP key, build the task,
/// create it, and spawn the agent via the standard flow (TasksStore.createTask +
/// AgentPillsManager.spawn). Used by both the Execute button in the connector
/// sheet AND the automation bridge (`POST /execute-export`) so headless e2e runs
/// drive the exact same path — no separate execution flow.
@MainActor
enum MemoryExportExecutor {
  struct Outcome: Sendable {
    let taskTitle: String
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

    _ = await TasksStore.shared.createTask(
      description: task.title, dueAt: Date(), priority: "high", tags: ["mcp-setup"])

    let model =
      ShortcutSettings.shared.selectedModel.isEmpty
      ? "claude-sonnet-4-6" : ShortcutSettings.shared.selectedModel
    let query = ProactiveTaskExecute.buildQuery(title: task.title, message: task.body)
    _ = AgentPillsManager.shared.spawn(
      query: query, model: model, systemPromptSuffix: ProactiveTaskExecute.systemPromptSuffix)

    return Outcome(taskTitle: task.title)
  }
}
