import AppKit
import Foundation

enum MemoryExportDestination: String, CaseIterable, Identifiable, Sendable {
  case notion
  case obsidian
  case chatgpt
  case claude
  case gemini
  case agents
  case claudeCode
  case codex

  var id: String { rawValue }

  /// Base of the hosted Omi API for this build — stable channel hits prod
  /// (api.omi.me), beta hits dev (api.omiapi.com). Always ends with "/".
  static var mcpBaseURL: String {
    DesktopBackendEnvironment.pythonBaseURL()
  }

  /// The hosted Omi MCP SSE endpoint every client connects to.
  static var mcpServerURL: String { "\(mcpBaseURL)v1/mcp/sse" }

  /// OAuth endpoints exposed by the same backend for MCP custom-connector setup.
  static var mcpAuthorizeURL: String { "\(mcpBaseURL)authorize" }
  static var mcpTokenURL: String { "\(mcpBaseURL)token" }

  var title: String {
    switch self {
    case .notion: return "Notion"
    case .obsidian: return "Obsidian"
    case .chatgpt: return "ChatGPT"
    case .claude: return "Claude"
    case .gemini: return "Gemini"
    case .agents: return "AI Agents"
    case .claudeCode: return "Claude Code"
    case .codex: return "Codex"
    }
  }

  var subtitle: String {
    switch self {
    case .notion: return "Copy-ready page export"
    case .obsidian: return "Choose once, refresh anytime"
    case .chatgpt: return "Live MCP or memory pack"
    case .claude: return "Live MCP or memory pack"
    case .gemini: return "Prompt + memory pack"
    case .agents: return "One prompt for your agent"
    case .claudeCode: return "Connect via MCP"
    case .codex: return "Connect via MCP"
    }
  }

  var description: String {
    switch self {
    case .notion: return "Copy a ready-to-paste memory page and jump into Notion."
    case .obsidian: return "Write Omi memories into your Obsidian vault."
    case .chatgpt: return "Connect over MCP so ChatGPT reads your memories live, or copy a memory pack."
    case .claude: return "Connect over MCP so Claude reads your memories live, or copy a memory pack."
    case .gemini: return "Copy the prompt and memory pack, then open Gemini."
    case .agents: return "Give your agent one prompt that connects Omi memories and this Mac."
    case .claudeCode: return "Add Omi as an MCP server so Claude Code always reads your memories."
    case .codex: return "Add Omi as an MCP server so Codex always reads your memories."
    }
  }

  var brand: ConnectorBrand {
    switch self {
    case .notion: return .notion
    case .obsidian: return .obsidian
    case .chatgpt: return .chatgpt
    case .claude: return .claude
    case .gemini: return .gemini
    case .agents: return .agents
    case .claudeCode: return .claudeCode
    case .codex: return .codex
    }
  }

  var isAutomated: Bool {
    switch self {
    case .obsidian:
      return true
    case .notion, .chatgpt, .claude, .gemini, .agents, .claudeCode, .codex:
      return false
    }
  }

  /// Whether this destination offers the live MCP connector flow.
  var supportsMCP: Bool {
    switch self {
    case .chatgpt, .claude, .claudeCode, .codex:
      return true
    case .notion, .obsidian, .gemini, .agents:
      return false
    }
  }

  /// How the "Execute" button performs the setup.
  /// - `.autonomous`: Omi runs a deterministic CLI step end-to-end (config write /
  ///   `claude mcp add`). Reliable for everyone.
  /// - `.assisted`: Omi opens the connector page and copies the key; the user does
  ///   the final clicks. Used for ChatGPT/Claude because fully autonomous browser
  ///   navigation of their connector UIs isn't reliable enough to promise.
  enum MCPExecuteKind { case autonomous, assisted }
  var mcpExecuteKind: MCPExecuteKind {
    switch self {
    case .chatgpt, .claude, .claudeCode, .codex: return .autonomous
    case .notion, .obsidian, .gemini, .agents: return .assisted
    }
  }

  var supportsAgentSetup: Bool {
    self == .agents
  }

  /// Whether this destination offers the classic copy/paste memory-pack export.
  var supportsMemoryPack: Bool {
    switch self {
    case .notion, .obsidian, .chatgpt, .claude, .gemini:
      return true
    case .agents, .claudeCode, .codex:
      return false
    }
  }

  var browserURL: URL? {
    switch self {
    case .notion:
      return URL(string: "https://www.notion.so/")
    case .obsidian:
      return nil
    case .chatgpt:
      return URL(string: "https://chatgpt.com/")
    case .claude:
      return URL(string: "https://claude.ai/new")
    case .gemini:
      return URL(string: "https://gemini.google.com/app")
    case .agents, .claudeCode, .codex:
      return nil
    }
  }

  var manualPrompt: String {
    switch self {
    case .notion, .agents, .claudeCode, .codex:
      return ""
    case .chatgpt:
      return """
        I’m attaching an Omi memory export. Read it carefully and keep the durable facts, preferences, projects, relationships, and goals as working context for future conversations with me. Start by giving me a concise profile summary of what you learned.
        """
    case .claude:
      return """
        I’m attaching an Omi memory export. Absorb the durable facts about me, including projects, habits, preferences, relationships, and goals, and use them as context for future conversations. Start by summarizing the most important things you learned about me.
        """
    case .gemini:
      return """
        I’m attaching an Omi memory export. Read it as persistent context about me and keep the durable facts, preferences, projects, and goals in mind for future chats. Start with a short profile summary of what stands out.
        """
    case .obsidian:
      return ""
    }
  }

  func clipboardText(for markdown: String) -> String {
    switch self {
    case .notion, .obsidian, .agents, .claudeCode, .codex:
      return markdown
    case .chatgpt, .claude, .gemini:
      return """
        \(manualPrompt)

        ---

        \(markdown)
        """
    }
  }

  // MARK: - MCP connection setup

  /// Per-client instructions for wiring Omi memory in over MCP, rendered with the user's key.
  func mcpSetup(key: String) -> MCPSetup? {
    let url = Self.mcpServerURL
    switch self {
    case .claude:
      return MCPSetup(
        serverURL: url,
        copyTitle: nil,
        copyText: nil,
        steps: [
          "Open claude.ai → Settings → Connectors → Add custom connector",
          "Name it “Omi Memory” and paste the server URL below",
          "Under Advanced settings set OAuth Client ID to “omi” and Client Secret to your key below",
          "Click Add, then Connect. Syncs to Claude desktop + mobile automatically.",
        ],
        openURL: URL(string: "https://claude.ai/settings/connectors"),
        openTitle: "Open Claude Connectors"
      )
    case .chatgpt:
      return MCPSetup(
        serverURL: url,
        copyTitle: nil,
        copyText: nil,
        steps: [
          "Open ChatGPT → Settings → Apps → Advanced, enable Developer mode",
          "Create app → name it “Omi Memory” and paste the server URL below",
          "Authentication: OAuth. In Advanced OAuth settings set Client ID “omi”, Client Secret to your key, token auth method “client_secret_post”",
          "Auth URL: \(Self.mcpAuthorizeURL) · Token URL: \(Self.mcpTokenURL)",
          "Create, then Connect. Syncs to ChatGPT desktop + mobile automatically.",
        ],
        openURL: URL(string: "https://chatgpt.com/"),
        openTitle: "Open ChatGPT"
      )
    case .claudeCode:
      return MCPSetup(
        serverURL: url,
        copyTitle: "Copy command",
        copyText:
          "claude mcp add --scope user --transport http omi-memory \(url) --header \"Authorization: Bearer \(key)\"",
        steps: [
          "Run the command below in your terminal",
          "It registers Omi at user scope, so every Claude Code project reads your memories",
        ],
        openURL: nil,
        openTitle: nil
      )
    case .codex:
      return MCPSetup(
        serverURL: url,
        copyTitle: "Copy config",
        copyText: """
          [mcp_servers.omi-memory]
          command = "npx"
          args = ["-y", "mcp-remote", "\(url)", "--header", "Authorization: Bearer \(key)"]
          """,
        steps: [
          "Add the block below to ~/.codex/config.toml",
          "Restart Codex — it will read your Omi memories over MCP",
        ],
        openURL: nil,
        openTitle: nil
      )
    case .notion, .obsidian, .gemini, .agents:
      return nil
    }
  }

  /// Title + body for an Omi task that asks Omi to perform this connection
  /// autonomously (driving the browser/terminal) via the standard execute flow.
  func omiExecutionTask(key: String) -> (title: String, body: String)? {
    guard let setup = mcpSetup(key: key) else { return nil }
    let clientName = title
    let taskTitle = "Connect my Omi memory to \(clientName) over MCP"
    var lines = [
      "Set up the Omi memory MCP connector in \(clientName) end-to-end for me so it can read my Omi memories. Use the browser/terminal as needed and confirm when it's connected.",
      "",
      "MCP server URL: \(setup.serverURL)",
      "My Omi MCP key: \(key)",
      "",
      "Steps:",
    ]
    for (index, step) in setup.steps.enumerated() {
      lines.append("\(index + 1). \(step)")
    }
    if let copyText = setup.copyText {
      lines.append("")
      lines.append("Command/config to run:")
      lines.append(copyText)
    }
    return (taskTitle, lines.joined(separator: "\n"))
  }

  fileprivate var notionTokenKey: String { "memoryExportNotionToken" }
  fileprivate var notionParentPageKey: String { "memoryExportNotionParentPageID" }
  fileprivate var obsidianVaultPathKey: String { "memoryExportObsidianVaultPath" }
  fileprivate var exportedCountKey: String { "memoryExportExportedCount.\(rawValue)" }
  fileprivate var lastExportedAtKey: String { "memoryExportLastExportedAt.\(rawValue)" }
  fileprivate var detailKey: String { "memoryExportDetail.\(rawValue)" }
  fileprivate var lastExportPathKey: String { "memoryExportLastExportPath.\(rawValue)" }
}

struct MemoryExportStatus: Sendable {
  let exportedCount: Int
  let lastExportedAt: Date?
  let detailText: String?
  let isConfigured: Bool
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

actor MemoryExportService {
  static let shared = MemoryExportService()

  private let defaults = UserDefaults.standard
  private let notionVersion = "2026-03-11"
  private let notionBaseURL = URL(string: "https://api.notion.com/v1")!

  func status(for destination: MemoryExportDestination) -> MemoryExportStatus {
    let exportedCount = max(defaults.integer(forKey: destination.exportedCountKey), 0)

    let lastExportedAt: Date?
    if defaults.object(forKey: destination.lastExportedAtKey) != nil {
      let timestamp = defaults.double(forKey: destination.lastExportedAtKey)
      lastExportedAt = timestamp > 0 ? Date(timeIntervalSince1970: timestamp) : nil
    } else {
      lastExportedAt = nil
    }

    let detailText = defaults.string(forKey: destination.detailKey)
    let isConfigured: Bool
    switch destination {
    case .obsidian:
      isConfigured = !(defaults.string(forKey: destination.obsidianVaultPathKey) ?? "").isEmpty
    case .agents:
      isConfigured = hasStoredMCPKey && LocalAgentAPISettings.isEnabled && LocalAgentAPISettings.storedToken() != nil
    case .claudeCode, .codex:
      isConfigured = hasStoredMCPKey
    case .notion, .chatgpt, .claude, .gemini:
      isConfigured = exportedCount > 0
    }

    return MemoryExportStatus(
      exportedCount: exportedCount,
      lastExportedAt: lastExportedAt,
      detailText: detailText,
      isConfigured: isConfigured
    )
  }

  func allStatuses() -> [MemoryExportDestination: MemoryExportStatus] {
    Dictionary(
      uniqueKeysWithValues: MemoryExportDestination.allCases.map { destination in
        (destination, status(for: destination))
      })
  }

  func notionConfiguration() -> (token: String, parentPageID: String) {
    (
      defaults.string(forKey: MemoryExportDestination.notion.notionTokenKey) ?? "",
      defaults.string(forKey: MemoryExportDestination.notion.notionParentPageKey) ?? ""
    )
  }

  func obsidianVaultPath() -> String {
    defaults.string(forKey: MemoryExportDestination.obsidian.obsidianVaultPathKey) ?? ""
  }

  // MARK: - MCP key

  private var mcpKeyDefaultsKey: String { "memoryExportMCPApiKey" }

  nonisolated var hasStoredMCPKey: Bool {
    !(UserDefaults.standard.string(forKey: "memoryExportMCPApiKey") ?? "").isEmpty
  }

  func storedMCPKey() -> String? {
    let value = defaults.string(forKey: mcpKeyDefaultsKey) ?? ""
    return value.isEmpty ? nil : value
  }

  /// Returns the cached MCP key, minting a fresh one via the backend on first use.
  func ensureMCPKey() async throws -> String {
    if let existing = storedMCPKey() {
      return existing
    }
    return try await createNewMCPKey()
  }

  /// Mint a fresh hosted MCP key and make future setup prompts use it.
  func createNewMCPKey() async throws -> String {
    let key = try await APIClient.shared.createMCPKey(name: "Omi Desktop")
    defaults.set(key, forKey: mcpKeyDefaultsKey)
    return key
  }

  func testAgentConnections(hostedKey: String, localToken: String) async throws -> AgentConnectionTestResult {
    async let hostedCount = testHostedMCPMemoryCount(key: hostedKey)
    async let localCount = testLocalAgentToolCount(token: localToken)
    return try await AgentConnectionTestResult(
      hostedMemoryCount: hostedCount,
      localToolCount: localCount
    )
  }

  private func testHostedMCPMemoryCount(key: String) async throws -> Int {
    guard let url = URL(string: MemoryExportDestination.mcpServerURL) else {
      throw MemoryExportError.requestFailed("Hosted MCP URL is invalid.")
    }

    let requestBody: [String: Any] = [
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/call",
      "params": [
        "name": "get_memories",
        "arguments": ["limit": 5],
      ],
    ]

    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
    request.httpBody = try JSONSerialization.data(withJSONObject: requestBody)

    let (data, response) = try await URLSession.shared.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw MemoryExportError.requestFailed("Hosted MCP returned an invalid response.")
    }
    guard (200...299).contains(httpResponse.statusCode) else {
      throw MemoryExportError.requestFailed("Hosted MCP returned HTTP \(httpResponse.statusCode).")
    }

    let rpc = try JSONSerialization.jsonObject(with: data) as? [String: Any]
    if let error = rpc?["error"] as? [String: Any],
      let message = error["message"] as? String
    {
      throw MemoryExportError.requestFailed("Hosted MCP failed: \(message)")
    }
    guard
      let result = rpc?["result"] as? [String: Any],
      let content = result["content"] as? [[String: Any]],
      let text = content.first?["text"] as? String,
      let textData = text.data(using: .utf8),
      let payload = try JSONSerialization.jsonObject(with: textData) as? [String: Any],
      let memories = payload["memories"] as? [Any]
    else {
      throw MemoryExportError.requestFailed("Hosted MCP did not return memory data.")
    }

    return memories.count
  }

  private func testLocalAgentToolCount(token: String) async throws -> Int {
    guard let url = URL(string: "\(LocalAgentAPISettings.serverURL)/v1/local/tools") else {
      throw MemoryExportError.requestFailed("Local Omi Desktop URL is invalid.")
    }

    var request = URLRequest(url: url)
    request.httpMethod = "GET"
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

    let (data, response) = try await URLSession.shared.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw MemoryExportError.requestFailed("Local Omi Desktop returned an invalid response.")
    }
    guard (200...299).contains(httpResponse.statusCode) else {
      throw MemoryExportError.requestFailed("Local Omi Desktop returned HTTP \(httpResponse.statusCode).")
    }

    guard
      let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let tools = payload["tools"] as? [Any]
    else {
      throw MemoryExportError.requestFailed("Local Omi Desktop did not return tools.")
    }

    return tools.count
  }

  static var omiAgentSkillText: String {
    """
    ---
    name: omi
    description: Use Omi memories, conversations, and same-Mac context through hosted MCP and the Omi local CLI.
    ---

    # Omi Agent Skill

    Use this skill when the user asks about their Omi memories, conversations, screen history, transcriptions, tasks, or wants you to use Omi context while helping.

    ## Discovery

    - Hosted MCP: list available tools before use. If `get_user_profile` exists, use it for a high-level summary. If it is absent, use `get_memories(limit=5)` and `search_memories`.
    - Local Omi CLI: run `omi --json local status` and `omi --json local tools` before local work. If status fails, Omi Desktop, the local URL, or the local token is not ready.

    ## Routing

    - Hosted MCP: durable memories, synced conversations, preferences, relationships, projects, goals, and profile-like context.
    - Local CLI: this Mac's screen history, screenshots, app/window activity, local transcriptions, read-only SQL, daily recaps, indexed files, local goals, and tasks.
    - Use `search_conversations` for synced meetings, calls, and remembered events. Use local transcription tables only for recent same-Mac or unsynced local history.
    - Use `omi --json local search-screen` for fuzzy Rewind/OCR questions. Use `omi --json local screenshot` only after a result returns a screenshot ID and the screenshot tool is present.
    - Use `omi --json local sql` for read-only counts, exact filters, local transcriptions, action items, indexed files, goals, and database questions.
    - Use `omi --json local task search` only if task tools are listed.
    - Use `omi --json local task complete` or `omi --json local task delete --yes` only when the user clearly asked you to complete or delete that task. If task tools are absent, do not mutate tasks.
    - Use `omi --json local call <tool> --args-json '{...}'` only when a listed local tool is not covered by a friendly command.
    - Create, edit, or delete hosted memories only after explicit user intent.

    ## Verification Checklist

    - Hosted MCP tools are listed.
    - Hosted memory query succeeds with `get_memories(limit=5)` or equivalent.
    - Local status succeeds with `omi --json local status`.
    - Local tools are listed with `omi --json local tools`.
    - Route only to tools that were discovered.

    ## Write Discipline

    - Do not create, edit, complete, or delete Omi memories or local tasks unless the user clearly asked for that change.
    - Prefer proposing the memory or task change first when intent is ambiguous.
    - Never treat transient screen activity as a durable memory without explicit user intent or strong evidence.

    ## Setup

    Hosted MCP endpoint: \(MemoryExportDestination.mcpServerURL)
    Authorization header: Bearer <omi_mcp_key>

    Local Omi Desktop CLI:
    - Install or update `omi-cli`.
    - Configure local access with `omi local configure --url <local_api_url> --token <omi_local_key>`.
    """
  }

  static func omiAgentSetupPrompt(
    hostedKey: String,
    localURL: String,
    localToken: String
  ) -> String {
    """
    Set up Omi access for this agent.

    1. Configure hosted Omi MCP for synced memories, conversations, and profile context.

    Hosted server URL:
    \(MemoryExportDestination.mcpServerURL)

    Hosted authorization header:
    Authorization: Bearer \(hostedKey)

    2. Configure the local Omi CLI for this Mac. Local access includes screen history, screenshot retrieval, local transcriptions, read-only SQL, daily recaps, indexed files, goals, app/window activity, and task search/complete/delete while Omi Desktop is running.

    Local Omi Desktop URL:
    \(localURL)

    Local Omi Desktop token:
    \(localToken)

    CLI setup:
    - If `omi` is not installed, install or update it with `pipx install omi-cli` or `pipx upgrade omi-cli`.
    - Run: `omi local configure --url \(localURL) --token \(localToken)`
    - Verify: `omi --json local status`
    - Discover local tools: `omi --json local tools`

    3. Save the Omi guide below. If this agent supports skills, install it as a skill named `omi`; otherwise save it in durable agent or project instructions.

    \(omiAgentSkillText)

    4. Verify setup:
    - List hosted MCP tools.
    - If hosted `get_user_profile` exists, call it. Otherwise call `get_memories` with `limit: 5`.
    - Run `omi --json local status`.
    - Run `omi --json local tools`.
    - Use only hosted and local tools that were discovered.
    """
  }

  func exportToNotion(token: String, parentPageID: String) async throws -> MemoryExportResult {
    let sanitizedToken = token.trimmingCharacters(in: .whitespacesAndNewlines)
    let sanitizedParentPageID = parentPageID.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !sanitizedToken.isEmpty, !sanitizedParentPageID.isEmpty else {
      throw MemoryExportError.invalidNotionConfiguration
    }

    let memories = try await fetchMemories(limit: 250)
    guard !memories.isEmpty else { throw MemoryExportError.noMemories }

    let pageTitle = "Omi Memory Export \(Self.exportTitleFormatter.string(from: Date()))"
    let pageID = try await createNotionPage(
      token: sanitizedToken,
      parentPageID: sanitizedParentPageID,
      title: pageTitle
    )
    try await appendNotionBlocks(
      token: sanitizedToken,
      pageID: pageID,
      memories: memories
    )

    defaults.set(sanitizedToken, forKey: MemoryExportDestination.notion.notionTokenKey)
    defaults.set(sanitizedParentPageID, forKey: MemoryExportDestination.notion.notionParentPageKey)

    let detail = "Exported to Notion"
    persistStatus(
      destination: .notion,
      exportedCount: memories.count,
      detailText: detail,
      filePath: nil
    )

    return MemoryExportResult(
      memoryCount: memories.count,
      detailText: detail,
      destinationURL: URL(string: "https://www.notion.so/"),
      fileURL: nil,
      clipboardText: nil
    )
  }

  func exportToObsidian(vaultURL: URL) async throws -> MemoryExportResult {
    let path = vaultURL.path.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !path.isEmpty else { throw MemoryExportError.invalidObsidianVault }

    let memories = try await fetchMemories(limit: 400)
    guard !memories.isEmpty else { throw MemoryExportError.noMemories }

    let exportDirectory = vaultURL.appendingPathComponent("Omi", isDirectory: true)
    try FileManager.default.createDirectory(
      at: exportDirectory,
      withIntermediateDirectories: true,
      attributes: nil
    )

    let exportFileURL = exportDirectory.appendingPathComponent("Memories.md")
    let markdown = buildMarkdownPack(memories: memories, destination: .obsidian)
    try markdown.write(to: exportFileURL, atomically: true, encoding: .utf8)

    defaults.set(path, forKey: MemoryExportDestination.obsidian.obsidianVaultPathKey)

    let detail = "Updated Obsidian vault"
    persistStatus(
      destination: .obsidian,
      exportedCount: memories.count,
      detailText: detail,
      filePath: exportFileURL.path
    )

    let openURL = obsidianOpenURL(vaultURL: vaultURL, notePath: "Omi/Memories")
    return MemoryExportResult(
      memoryCount: memories.count,
      detailText: detail,
      destinationURL: openURL,
      fileURL: exportFileURL,
      clipboardText: nil
    )
  }

  func prepareManualExport(for destination: MemoryExportDestination) async throws
    -> MemoryExportResult
  {
    precondition(!destination.isAutomated, "prepareManualExport only supports manual destinations")

    let memories = try await fetchMemories(limit: 400)
    guard !memories.isEmpty else { throw MemoryExportError.noMemories }

    let directory = try exportDirectory()
    let fileURL = directory.appendingPathComponent(
      "\(destination.rawValue)-memory-pack-\(Self.fileStampFormatter.string(from: Date())).md"
    )

    let markdown = buildMarkdownPack(memories: memories, destination: destination)
    try markdown.write(to: fileURL, atomically: true, encoding: .utf8)

    let detail = "Memory pack ready"
    persistStatus(
      destination: destination,
      exportedCount: memories.count,
      detailText: detail,
      filePath: fileURL.path
    )

    return MemoryExportResult(
      memoryCount: memories.count,
      detailText: detail,
      destinationURL: destination.browserURL,
      fileURL: fileURL,
      clipboardText: destination.clipboardText(for: markdown)
    )
  }

  private func fetchMemories(limit: Int) async throws -> [ServerMemory] {
    do {
      let remoteMemories = try await APIClient.shared.getMemories(limit: limit)
      if !remoteMemories.isEmpty {
        return remoteMemories
      }
    } catch {
      log("MemoryExportService: Remote memory fetch failed, falling back to local cache: \(error)")
    }

    let localMemories = try await MemoryStorage.shared.getLocalMemories(limit: limit)
    if !localMemories.isEmpty {
      return localMemories
    }

    throw MemoryExportError.noMemories
  }

  private func buildMarkdownPack(
    memories: [ServerMemory],
    destination: MemoryExportDestination
  ) -> String {
    var lines: [String] = [
      "# Omi Memory Export",
      "",
      "Generated: \(Self.exportTitleFormatter.string(from: Date()))",
      "Destination: \(destination.title)",
      "Total memories: \(memories.count)",
      "",
      "## Durable memories",
    ]

    for memory in memories {
      let sourceApp = memory.sourceApp?.trimmingCharacters(in: .whitespacesAndNewlines)
      let sourcePrefix = (sourceApp?.isEmpty == false) ? "[\(sourceApp!)] " : ""
      let content = memory.content
        .replacingOccurrences(of: "\n", with: " ")
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard !content.isEmpty else { continue }
      lines.append("- \(sourcePrefix)\(content)")
    }

    lines.append("")
    lines.append("## How to use this")
    if destination.isAutomated {
      lines.append("This export was generated by Omi and can be refreshed at any time.")
    } else {
      lines.append(
        "Upload or paste this export into \(destination.title) together with the copied prompt.")
    }

    return lines.joined(separator: "\n")
  }

  private func exportDirectory() throws -> URL {
    let downloads =
      FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
      ?? FileManager.default.homeDirectoryForCurrentUser
    let directory = downloads.appendingPathComponent("Omi Exports", isDirectory: true)
    try FileManager.default.createDirectory(
      at: directory,
      withIntermediateDirectories: true,
      attributes: nil
    )
    return directory
  }

  private func persistStatus(
    destination: MemoryExportDestination,
    exportedCount: Int,
    detailText: String?,
    filePath: String?
  ) {
    defaults.set(exportedCount, forKey: destination.exportedCountKey)
    defaults.set(Date().timeIntervalSince1970, forKey: destination.lastExportedAtKey)
    defaults.set(detailText, forKey: destination.detailKey)
    if let filePath {
      defaults.set(filePath, forKey: destination.lastExportPathKey)
    }
  }

  private func createNotionPage(token: String, parentPageID: String, title: String) async throws
    -> String
  {
    let url = notionBaseURL.appendingPathComponent("pages")
    var request = notionRequest(url: url, token: token)
    request.httpMethod = "POST"

    let body: [String: Any] = [
      "parent": ["page_id": parentPageID],
      "properties": [
        "title": [
          "title": [
            [
              "type": "text",
              "text": ["content": title],
            ]
          ]
        ]
      ],
    ]

    request.httpBody = try JSONSerialization.data(withJSONObject: body)
    let (data, response) = try await URLSession.shared.data(for: request)
    try validateNotionResponse(data: data, response: response)

    guard
      let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let pageID = json["id"] as? String
    else {
      throw MemoryExportError.invalidNotionResponse
    }

    return pageID
  }

  private func appendNotionBlocks(token: String, pageID: String, memories: [ServerMemory])
    async throws
  {
    let url = notionBaseURL.appendingPathComponent("blocks/\(pageID)/children")
    let chunks = notionChildren(memories: memories).chunked(into: 100)

    for chunk in chunks where !chunk.isEmpty {
      var request = notionRequest(url: url, token: token)
      request.httpMethod = "PATCH"
      request.httpBody = try JSONSerialization.data(withJSONObject: ["children": chunk])
      let (data, response) = try await URLSession.shared.data(for: request)
      try validateNotionResponse(data: data, response: response)
    }
  }

  private func notionRequest(url: URL, token: String) -> URLRequest {
    var request = URLRequest(url: url)
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue(notionVersion, forHTTPHeaderField: "Notion-Version")
    request.timeoutInterval = 30
    return request
  }

  private func validateNotionResponse(data: Data, response: URLResponse) throws {
    guard let httpResponse = response as? HTTPURLResponse else {
      throw MemoryExportError.requestFailed("Notion did not return a valid HTTP response.")
    }

    guard (200..<300).contains(httpResponse.statusCode) else {
      let message: String
      if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
        let detail = json["message"] as? String
      {
        message = detail
      } else {
        message = HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode)
      }
      throw MemoryExportError.requestFailed("Notion export failed: \(message)")
    }
  }

  private func notionChildren(memories: [ServerMemory]) -> [[String: Any]] {
    var children: [[String: Any]] = [
      headingBlock(level: 1, text: "Omi Memory Export"),
      paragraphBlock(text: "Generated \(Self.exportTitleFormatter.string(from: Date()))"),
      headingBlock(level: 2, text: "Durable memories"),
    ]

    children.append(
      contentsOf: memories.compactMap { memory in
        let content = memory.content
          .replacingOccurrences(of: "\n", with: " ")
          .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty else { return nil }
        return bulletBlock(text: String(content.prefix(1800)))
      }
    )

    return children
  }

  private func headingBlock(level: Int, text: String) -> [String: Any] {
    let type = "heading_\(level)"
    return [
      "object": "block",
      "type": type,
      type: ["rich_text": richText(text: text)],
    ]
  }

  private func paragraphBlock(text: String) -> [String: Any] {
    [
      "object": "block",
      "type": "paragraph",
      "paragraph": ["rich_text": richText(text: text)],
    ]
  }

  private func bulletBlock(text: String) -> [String: Any] {
    [
      "object": "block",
      "type": "bulleted_list_item",
      "bulleted_list_item": ["rich_text": richText(text: text)],
    ]
  }

  private func richText(text: String) -> [[String: Any]] {
    [
      [
        "type": "text",
        "text": ["content": text],
      ]
    ]
  }

  private func obsidianOpenURL(vaultURL: URL, notePath: String) -> URL? {
    var components = URLComponents()
    components.scheme = "obsidian"
    components.host = "open"
    components.queryItems = [
      URLQueryItem(name: "vault", value: vaultURL.lastPathComponent),
      URLQueryItem(name: "file", value: notePath),
    ]
    return components.url
  }

  private static let exportTitleFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .short
    return formatter
  }()

  private static let fileStampFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyyMMdd-HHmm"
    return formatter
  }()
}

extension Array {
  fileprivate func chunked(into size: Int) -> [[Element]] {
    guard size > 0 else { return [self] }
    return stride(from: 0, to: count, by: size).map { start in
      Array(self[start..<Swift.min(start + size, count)])
    }
  }
}
