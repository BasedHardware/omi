import Foundation

struct MemoryExportStatus: Sendable {
  let exportedCount: Int
  let lastExportedAt: Date?
  let detailText: String?
  let isConfigured: Bool
  let hasConnection: Bool
}

struct MCPSetupCompletionSummary: Equatable, Sendable {
  let title: String
  let subtitle: String
}

struct MemoryExportConnectionPresentation: Equatable {
  let primaryActionTitle: String?
  let completion: MCPSetupCompletionSummary?

  static func make(
    destination: MemoryExportDestination,
    status: MemoryExportStatus?,
    isRunning: Bool,
    accessibilityPreflightMissing: Bool = false
  ) -> MemoryExportConnectionPresentation {
    if status?.hasConnection == true {
      return MemoryExportConnectionPresentation(
        primaryActionTitle: nil,
        completion: destination.mcpSetupCompletionSummary
      )
    }

    let title: String
    if isRunning {
      title = "Connecting…"
    } else {
      switch destination.mcpExecuteKind {
      case .directoryApp:
        title = "Add Omi to ChatGPT"
      case .localAutonomous:
        title = "Do it for me"
      case .browserAutonomous:
        title = accessibilityPreflightMissing ? "Grant Accessibility" : "Do it for me"
      case .assisted:
        title = destination.assistedOverlayHint != nil ? "Open & guide me" : "Open & copy key"
      }
    }

    return MemoryExportConnectionPresentation(primaryActionTitle: title, completion: nil)
  }
}

/// Rendered MCP connection instructions for a single client.
struct MCPSetup: Sendable {
  let serverURL: String
  let copyTitle: String?
  let copyText: String?
  let steps: [String]
  let openURL: URL?
  let openTitle: String?
}

struct MemoryExportResult: Sendable {
  let memoryCount: Int
  let detailText: String?
  let destinationURL: URL?
  let fileURL: URL?
  let clipboardText: String?
}

struct AgentConnectionTestResult: Sendable {
  let hostedMemoryCount: Int
  let localToolCount: Int

  var summary: String {
    "Connection looks good: Omi returned \(hostedMemoryCount) hosted memories, and Desktop shared \(localToolCount) local tools."
  }
}

enum MemoryExportError: LocalizedError {
  case noMemories
  case invalidNotionConfiguration
  case invalidNotionResponse
  case invalidObsidianVault
  case requestFailed(String)

  var errorDescription: String? {
    switch self {
    case .noMemories:
      return "There are no memories available to export yet."
    case .invalidNotionConfiguration:
      return "Enter both a Notion integration token and a parent page ID."
    case .invalidNotionResponse:
      return "Notion returned an unexpected response."
    case .invalidObsidianVault:
      return "Choose a valid Obsidian vault folder first."
    case .requestFailed(let message):
      return message
    }
  }
}
