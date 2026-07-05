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
  case openclaw
  case hermes

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

  /// Registered OAuth client for ChatGPT custom connectors on this backend.
  /// Prod registers `omi-chatgpt-prod` as a PUBLIC PKCE client — the token
  /// endpoint rejects any client secret for it, so setup must leave the
  /// secret blank. Dev registers `omi-chatgpt-dev`.
  static var chatgptOAuthClientID: String {
    mcpBaseURL.contains("api.omi.me") ? "omi-chatgpt-prod" : "omi-chatgpt-dev"
  }

  var cloudOAuthClientID: String? {
    switch self {
    case .chatgpt: return Self.chatgptOAuthClientID
    case .claude: return "omi-claude-prod"
    case .notion, .obsidian, .gemini, .agents, .claudeCode, .codex, .openclaw, .hermes:
      return nil
    }
  }

  var cloudOAuthClientSecret: String? {
    switch self {
    case .chatgpt, .claude:
      return nil
    case .notion, .obsidian, .gemini, .agents, .claudeCode, .codex, .openclaw, .hermes:
      return nil
    }
  }

  var cloudTokenAuthMethod: String? {
    switch self {
    case .chatgpt: return "none"
    case .claude:
      return nil
    case .notion, .obsidian, .gemini, .agents, .claudeCode, .codex, .openclaw, .hermes:
      return nil
    }
  }

  var usesPublicCloudOAuthClient: Bool {
    cloudOAuthClientID != nil && cloudOAuthClientSecret == nil
  }

  var requiresHostedMCPKeyForSetup: Bool {
    !usesPublicCloudOAuthClient
  }

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
    case .openclaw: return "OpenClaw"
    case .hermes: return "Hermes"
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
    case .openclaw: return "Memory bank for OpenClaw"
    case .hermes: return "Memory bank for Hermes"
    }
  }

  var description: String {
    switch self {
    case .notion: return "Copy a ready-to-paste memory page and jump into Notion."
    case .obsidian: return "Write Omi memories into your Obsidian vault."
    case .chatgpt:
      return "Connect over MCP so ChatGPT reads your memories live, or copy a memory pack."
    case .claude:
      return "Connect over MCP so Claude reads your memories live, or copy a memory pack."
    case .gemini: return "Copy the prompt and memory pack, then open Gemini."
    case .agents: return "Give your agent one prompt that connects Omi memories and this Mac."
    case .claudeCode: return "Add Omi as an MCP server so Claude Code always reads your memories."
    case .codex: return "Add Omi as an MCP server so Codex always reads your memories."
    case .openclaw: return "Wire Omi memory into OpenClaw so your agent reads your memories."
    case .hermes: return "Wire Omi memory into Hermes so your agent reads your memories."
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
    case .openclaw: return .openclaw
    case .hermes: return .hermes
    }
  }

  var isAutomated: Bool {
    switch self {
    case .obsidian:
      return true
    case .notion, .chatgpt, .claude, .gemini, .agents, .claudeCode, .codex, .openclaw, .hermes:
      return false
    }
  }

  /// Whether this destination offers the live MCP connector flow.
  var supportsMCP: Bool {
    switch self {
    case .chatgpt, .claude, .claudeCode, .codex, .openclaw, .hermes:
      return true
    case .notion, .obsidian, .gemini, .agents:
      return false
    }
  }

  /// How the "Do it for me" button performs setup.
  /// - `.localAutonomous`: deterministic local CLI/config/file work.
  /// - `.browserAutonomous`: open the cloud connector in the user's default
  ///   signed-in browser and use native macOS automation, with assisted fallback
  ///   on blockers. Currently unmapped: ChatGPT/Claude moved to `.assisted`
  ///   because cross-browser AX automation is too brittle — see
  ///   docs/cloud-connectors-roadmap.md before mapping anything back here.
  /// - `.assisted`: deterministic open + copy, with an on-screen guidance card
  ///   for cloud connectors. The user performs the final paste/click.
  enum MCPExecuteKind { case localAutonomous, browserAutonomous, assisted }
  var mcpExecuteKind: MCPExecuteKind {
    switch self {
    case .claudeCode, .codex, .openclaw, .hermes: return .localAutonomous
    case .chatgpt, .claude, .notion, .obsidian, .gemini, .agents: return .assisted
    }
  }

  var supportsAgentSetup: Bool {
    self == .agents
  }

  var hasLocallyVerifiableLiveSetup: Bool {
    switch self {
    case .agents, .claudeCode, .codex, .openclaw, .hermes:
      return true
    case .notion, .obsidian, .chatgpt, .claude, .gemini:
      return false
    }
  }

  /// Whether this destination offers the classic copy/paste memory-pack export.
  var supportsMemoryPack: Bool {
    switch self {
    case .notion, .obsidian, .chatgpt, .claude, .gemini:
      return true
    case .agents, .claudeCode, .codex, .openclaw, .hermes:
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
    case .agents, .claudeCode, .codex, .openclaw, .hermes:
      return nil
    }
  }

  var manualPrompt: String {
    switch self {
    case .notion, .agents, .claudeCode, .codex, .openclaw, .hermes:
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
    case .notion, .obsidian, .agents, .claudeCode, .codex, .openclaw, .hermes:
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
          "Open Claude → Customize → Connectors → Add custom connector",
          "Copy Name and Remote MCP server URL into the first two Claude fields",
          "Open Advanced settings, set OAuth Client ID “\(cloudOAuthClientID ?? "")”, and leave OAuth Client Secret blank",
          "Click Add, then Connect. Syncs to Claude desktop + mobile automatically.",
        ],
        openURL: URL(string: "https://claude.ai/customize/connectors?modal=add-custom-connector"),
        openTitle: "Add Claude Connector"
      )
    case .chatgpt:
      return MCPSetup(
        serverURL: url,
        copyTitle: nil,
        copyText: nil,
        steps: [
          "Open ChatGPT → Settings → Apps → Advanced, then enable Developer mode",
          "Click Create app, then fill the first visible fields: Name “Omi Memory”, Connection / server URL, and Authentication OAuth",
          "Paste OAuth Client ID “\(cloudOAuthClientID ?? "")”, leave Client Secret blank, set token auth method “\(cloudTokenAuthMethod ?? "none")”, Auth URL, and Token URL",
          "Click Create app, then Connect. Syncs to ChatGPT desktop + mobile automatically.",
        ],
        openURL: URL(string: "https://chatgpt.com/#settings/Connectors"),
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
    case .hermes:
      return MCPSetup(
        serverURL: url,
        copyTitle: "Copy config",
        copyText: """
          omi-memory:
            command: npx
            args: ["-y", "mcp-remote", "\(url)", "--header", "Authorization: Bearer \(key)"]
          """,
        steps: [
          "Add the block below under mcp_servers: in ~/.hermes/config.yaml",
          "Restart Hermes — it reads your Omi memories over MCP and searches them first",
        ],
        openURL: nil,
        openTitle: nil
      )
    case .openclaw:
      let serverJSON =
        #"{"enabled":true,"url":"\#(url)","transport":"streamable-http","headers":{"Authorization":"Bearer \#(key)"}}"#
      return MCPSetup(
        serverURL: url,
        copyTitle: "Copy command",
        copyText: """
          openclaw mcp set omi-memory \(Self.shellQuote(serverJSON))
          openclaw mcp reload
          """,
        steps: [
          "Run the command below to add the Omi MCP server to ~/.openclaw/openclaw.json",
          "Reload OpenClaw MCP so open sessions rebuild their tool list",
          "Add a SOUL.md note asking OpenClaw to search Omi memory first",
        ],
        openURL: nil,
        openTitle: nil
      )
    case .notion, .obsidian, .gemini, .agents:
      return nil
    }
  }

  var mcpSetupCompletionSummary: MCPSetupCompletionSummary {
    switch self {
    case .codex:
      return MCPSetupCompletionSummary(
        title: "Setup complete",
        subtitle: "Restart Codex to load Omi Memory."
      )
    case .claudeCode:
      return MCPSetupCompletionSummary(
        title: "Setup complete",
        subtitle: "Restart Claude Code to load Omi Memory."
      )
    case .hermes:
      return MCPSetupCompletionSummary(
        title: "Setup complete",
        subtitle: "Restart Hermes to load Omi Memory."
      )
    case .openclaw:
      return MCPSetupCompletionSummary(
        title: "Connected",
        subtitle: "OpenClaw is ready to read Omi Memory."
      )
    case .chatgpt, .claude:
      return MCPSetupCompletionSummary(
        title: "Connected",
        subtitle: "\(title) can read Omi Memory."
      )
    case .notion, .obsidian, .gemini, .agents:
      return MCPSetupCompletionSummary(
        title: "Setup complete",
        subtitle: "\(title) is ready."
      )
    }
  }

  private static func shellQuote(_ value: String) -> String {
    "'\(value.replacingOccurrences(of: "'", with: "'\\''"))'"
  }

  /// Title + body for an Omi task that asks Omi to perform this connection
  /// autonomously (driving the browser/terminal) via the standard execute flow.
  func omiExecutionTask(key: String) -> (title: String, body: String)? {
    guard let setup = mcpSetup(key: key) else { return nil }
    let clientName = title
    let taskTitle = "Connect my Omi memory to \(clientName) over MCP"
    var lines = [
      "Set up the Omi memory MCP connector in \(clientName) end-to-end for me so it can read my Omi memories. Complete this autonomously if the user is already signed in and the UI allows it. Hand back only if sign-in, missing workspace permission, security confirmation, or changed UI blocks you.",
      "",
    ]
    if self == .claude {
      lines.append(contentsOf: [
        "Claude custom connector fields:",
        "Name: Omi Memory",
        "Remote MCP server URL: \(setup.serverURL)",
        "OAuth Client ID: \(cloudOAuthClientID ?? "")",
        "Leave OAuth Client Secret blank.",
        "",
      ])
    } else {
      lines.append(contentsOf: [
        "MCP server URL: \(setup.serverURL)",
        "My Omi MCP key: \(key)",
        "",
      ])
    }
    lines.append("Steps:")
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

  func guidedBrowserSetupTask(key: String, browserName: String) -> (title: String, body: String)? {
    guard let setup = mcpSetup(key: key), let openURL = setup.openURL else { return nil }
    let taskTitle = "Connect my Omi memory to \(title) over MCP"
    let values: [String]
    switch self {
    case .chatgpt:
      values = [
        "Name: Omi Memory",
        "Remote MCP server URL: \(setup.serverURL)",
        "Authentication: OAuth",
        "OAuth Client ID: \(cloudOAuthClientID ?? "")",
        "Token auth method: \(cloudTokenAuthMethod ?? "")",
        "Auth URL: \(Self.mcpAuthorizeURL)",
        "Token URL: \(Self.mcpTokenURL)",
      ]
    case .claude:
      values = [
        "Name: Omi Memory",
        "Remote MCP server URL: \(setup.serverURL)",
        "OAuth Client ID: \(cloudOAuthClientID ?? "")",
      ]
    default:
      return nil
    }

    let valuesJSON =
      "{"
      + values.map { line -> String? in
        let parts = line.split(separator: ":", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { return nil }
        let key = parts[0].trimmingCharacters(in: .whitespaces)
        let value = parts[1].trimmingCharacters(in: .whitespaces)
        return "\"\(Self.jsonEscaped(key))\":\"\(Self.jsonEscaped(value))\""
      }
      .compactMap { $0 }
      .joined(separator: ",")
      + "}"

    var nativeToolArgs: [(String, String)] = [
      ("provider", rawValue),
      ("name", "Omi Memory"),
      ("server_url", setup.serverURL),
      ("submit", "true"),
    ]
    if let clientID = cloudOAuthClientID {
      nativeToolArgs.append(("oauth_client_id", clientID))
    }
    if let clientSecret = cloudOAuthClientSecret {
      nativeToolArgs.append(("oauth_client_secret", clientSecret))
    }
    if self == .chatgpt {
      // Public PKCE client — no client secret; the token endpoint rejects one.
      // oauth_client_secret is required by the tool schema — pass empty string.
      nativeToolArgs.append(contentsOf: [
        ("authentication", "OAuth"),
        ("token_auth_method", cloudTokenAuthMethod ?? "none"),
        ("auth_url", Self.mcpAuthorizeURL),
        ("token_url", Self.mcpTokenURL),
      ])
    } else if !usesPublicCloudOAuthClient {
      nativeToolArgs.append(contentsOf: [
        ("oauth_client_id", "omi"),
        ("oauth_client_secret", key),
      ])
    }
    let nativeToolJSON =
      "{"
      + nativeToolArgs.map { key, value in
        if key == "submit" {
          return "\"\(key)\":\(value)"
        }
        return "\"\(key)\":\"\(Self.jsonEscaped(value))\""
      }
      .joined(separator: ",")
      + "}"

    var lines = [
      "Finish connecting Omi memory to \(title) in \(browserName).",
      "FIRST ACTION: call the `fill_cloud_connector_form` tool with this exact JSON, then read its result before doing anything else:",
      nativeToolJSON,
      "Only fall back to bash, osascript, screenshots, or keyboard automation if that tool reports a missing form, missing required field, or missing permission.",
      "Use macOS UI automation first: Accessibility, System Events, AppleScript/osascript, screenshots, keyboard shortcuts, and pasteboard are available. Use browser tools only if they are already available; do not require the user to install a browser extension.",
      "This is an autonomous setup attempt. Do not stop after opening the page; navigate and fill the connector/app form if the user is already signed in.",
      "Use a new browser tab when possible, keep all work in that tab, and do not disturb the user's other tabs.",
      "Before every click, key press, or paste, verify the frontmost app is \(browserName), the visible URL is the expected \(title) setup page, and the next control/state is clearly identified. Do not use blind coordinate clicks or repeated Tab/Enter loops on an unverified page.",
      "If the user is signed out, developer/custom connector permission is missing, a CAPTCHA/security prompt appears, or the UI no longer has the expected controls, stop and report the exact blocker plus the next click/value needed.",
      "",
      "Start URL: \(openURL.absoluteString)",
      "Setup values JSON: \(valuesJSON)",
      "Leave OAuth Client Secret blank if the form shows it.",
      "",
      "Values to enter:",
    ]
    lines.append(contentsOf: values.map { "- \($0)" })
    lines.append("")
    lines.append("Automation ladder:")
    lines.append(
      "1. Bring \(browserName) forward and use keyboard shortcuts/System Events to navigate if needed. Prefer Cmd-L, paste the Start URL, Enter, then wait for the page to load."
    )
    lines.append(
      "2. If \(browserName) has a Chrome-style AppleScript dictionary, use osascript to set the active tab URL and `execute javascript` to inspect labels, find inputs/buttons, and fill matching fields."
    )
    lines.append(
      "3. If JavaScript execution is unavailable, use screenshots plus Accessibility/System Events: click by visible labels, use Tab/Shift-Tab to move through fields, paste exact values from the setup JSON, and read visible text after each major step."
    )
    lines.append(
      "4. Keep using the browser that is already open/signed in. Do not launch a clean Playwright profile unless the user is already signed in there."
    )
    lines.append(
      "5. Do not install browser extensions. If the only blocker is lack of extension-based browser tools, continue with System Events instead."
    )
    lines.append("")
    lines.append("Expected path:")
    for (index, step) in setup.steps.enumerated() {
      lines.append("\(index + 1). \(step)")
    }
    lines.append("")
    lines.append(
      "After setup, verify that \(title) shows Omi Memory as connected or available. If a final OAuth consent/connect button appears, click it only when it is clearly for Omi Memory."
    )
    return (taskTitle, lines.joined(separator: "\n"))
  }

  /// Field-by-field payload for assisted cloud setup — rendered as copy rows on
  /// the on-screen guidance card so the user transfers one value at a time.
  func assistedSetupFields(key: String) -> [CloudConnectorCopyField]? {
    assistedSetupSections(key: key).map(CloudConnectorCopySection.flattenedFields)
  }

  /// Sectioned field payload for assisted cloud setup. Use sections when the
  /// provider form hides some fields behind an advanced disclosure.
  func assistedSetupSections(key: String) -> [CloudConnectorCopySection]? {
    guard let setup = mcpSetup(key: key) else { return nil }
    switch self {
    case .claude:
      // Public OAuth client: match the manual setup copy and native automation.
      // Claude may render a secret field, but the backend expects it to stay blank.
      return [
        CloudConnectorCopySection(
          id: "main_fields",
          title: "Main fields",
          fields: [
            CloudConnectorCopyField(id: "name", label: "Name", value: "Omi Memory"),
            CloudConnectorCopyField(
              id: "server_url", label: "Remote MCP server URL", value: setup.serverURL),
          ]),
        CloudConnectorCopySection(
          id: "advanced_settings",
          title: "Advanced settings",
          fields: [
            CloudConnectorCopyField(
              id: "oauth_client_id", label: "OAuth Client ID", value: cloudOAuthClientID ?? ""),
            CloudConnectorCopyField(
              id: "oauth_client_secret", label: "OAuth Client Secret", value: "", masksValue: false),
          ]),
      ]
    case .chatgpt:
      // Public PKCE client: the backend rejects token requests that carry a
      // client secret, so the form's Client Secret field must stay empty.
      return [
        CloudConnectorCopySection(
          id: "visible_fields",
          title: "Main fields",
          fields: [
            CloudConnectorCopyField(id: "name", label: "Name", value: "Omi Memory"),
            CloudConnectorCopyField(
              id: "server_url", label: "Connection / server URL", value: setup.serverURL),
            CloudConnectorCopyField(id: "authentication", label: "Authentication", value: "OAuth"),
          ]),
        CloudConnectorCopySection(
          id: "advanced_oauth_settings",
          title: "Advanced OAuth settings",
          fields: [
            CloudConnectorCopyField(
              id: "oauth_client_id", label: "OAuth Client ID", value: Self.chatgptOAuthClientID),
            CloudConnectorCopyField(
              id: "oauth_client_secret", label: "OAuth Client Secret", value: "", masksValue: false),
            CloudConnectorCopyField(
              id: "token_auth_method", label: "Token auth method", value: cloudTokenAuthMethod ?? "none",
              masksValue: false),
            CloudConnectorCopyField(id: "auth_url", label: "Auth URL", value: Self.mcpAuthorizeURL),
            CloudConnectorCopyField(
              id: "token_url", label: "Token URL", value: Self.mcpTokenURL, masksValue: false),
          ]),
      ]
    default:
      return nil
    }
  }

  /// Short on-screen guidance card shown right after Omi opens the provider page.
  var assistedOverlayHint: (title: String, subtitle: String)? {
    switch self {
    case .claude:
      return (
        "Finish in Claude",
        "Copy each value into the Add custom connector form, then click Add and Connect."
      )
    case .chatgpt:
      return (
        "Finish in ChatGPT",
        "In Settings → Apps → Advanced, enable Developer mode. Then click Create app and fill the fields below."
      )
    default:
      return nil
    }
  }

  private static func jsonEscaped(_ value: String) -> String {
    value
      .replacingOccurrences(of: "\\", with: "\\\\")
      .replacingOccurrences(of: "\"", with: "\\\"")
      .replacingOccurrences(of: "\n", with: "\\n")
  }

  fileprivate var notionTokenKey: String { "memoryExportNotionToken" }
  fileprivate var notionParentPageKey: String { "memoryExportNotionParentPageID" }
  fileprivate var obsidianVaultPathKey: String { "memoryExportObsidianVaultPath" }
  fileprivate var exportedCountKey: String { "memoryExportExportedCount.\(rawValue)" }
  fileprivate var lastExportedAtKey: String { "memoryExportLastExportedAt.\(rawValue)" }
  fileprivate var detailKey: String { "memoryExportDetail.\(rawValue)" }
  fileprivate var lastExportPathKey: String { "memoryExportLastExportPath.\(rawValue)" }
  fileprivate var connectedAtKey: String { "memoryExportConnectedAt.\(rawValue)" }
}

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

actor MemoryExportService {
  static let shared = MemoryExportService()

  private static let authUserIDDefaultsKey = "auth_userId"
  private static let mcpKeyDefaultsKey = "memoryExportMCPApiKey"
  private static let mcpKeyOwnerDefaultsKey = "memoryExportMCPApiKeyOwnerUserId"
  private static let mcpKeyCreatedAtDefaultsKey = "memoryExportMCPApiKeyCreatedAt"

  private let defaults = UserDefaults.standard
  private let notionVersion = "2026-03-11"
  private let notionBaseURL = URL(string: "https://api.notion.com/v1")!
  private var mcpKeyWarmTask: (ownerUserId: String, id: UUID, task: Task<String, Error>)?

  func status(for destination: MemoryExportDestination) -> MemoryExportStatus {
    let currentMCPKey = storedMCPKey()
    let localConnections: Set<MemoryExportDestination> = destination.supportsMCP
      ? MemoryExportConnectionDetector.scanLocalMCPConnections(for: destination, matchingKey: currentMCPKey)
      : []
    return status(for: destination, localMCPConnections: localConnections)
  }

  private func status(
    for destination: MemoryExportDestination,
    localMCPConnections: Set<MemoryExportDestination>
  ) -> MemoryExportStatus {
    let exportedCount = max(defaults.integer(forKey: destination.exportedCountKey), 0)

    let lastExportedAt: Date?
    if defaults.object(forKey: destination.lastExportedAtKey) != nil {
      let timestamp = defaults.double(forKey: destination.lastExportedAtKey)
      lastExportedAt = timestamp > 0 ? Date(timeIntervalSince1970: timestamp) : nil
    } else {
      lastExportedAt = nil
    }

    let detailText = defaults.string(forKey: destination.detailKey)
    let hasLocalMCPConnection = localMCPConnections.contains(destination)
    let hasConnectedTimestamp = defaults.double(forKey: destination.connectedAtKey) > 0
    let hasConnection: Bool
    switch destination {
    case .claudeCode, .codex, .openclaw, .hermes:
      hasConnection = hasLocalMCPConnection
    case .claude:
      hasConnection = exportedCount > 0 || hasConnectedTimestamp || hasLocalMCPConnection
    case .chatgpt, .notion, .obsidian, .gemini, .agents:
      hasConnection = exportedCount > 0 || hasConnectedTimestamp || hasLocalMCPConnection
    }
    let isConfigured: Bool
    switch destination {
    case .obsidian:
      isConfigured = !(defaults.string(forKey: destination.obsidianVaultPathKey) ?? "").isEmpty
    case .agents:
      isConfigured =
        hasStoredMCPKey && LocalAgentAPISettings.isEnabled
        && LocalAgentAPISettings.storedToken() != nil
    case .claudeCode, .codex, .openclaw, .hermes:
      isConfigured = hasConnection
    case .chatgpt, .claude:
      isConfigured = hasConnection
    case .notion, .gemini:
      isConfigured = exportedCount > 0
    }

    return MemoryExportStatus(
      exportedCount: exportedCount,
      lastExportedAt: lastExportedAt,
      detailText: detailText,
      isConfigured: isConfigured,
      hasConnection: hasConnection
    )
  }

  func allStatuses() -> [MemoryExportDestination: MemoryExportStatus] {
    let localConnections = MemoryExportConnectionDetector.scanLocalMCPConnections(matchingKey: storedMCPKey())
    return Dictionary(
      uniqueKeysWithValues: MemoryExportDestination.allCases.map { destination in
        (destination, status(for: destination, localMCPConnections: localConnections))
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

  nonisolated var hasStoredMCPKey: Bool {
    let defaults = UserDefaults.standard
    guard
      let userId = Self.normalizedDefaultsString(defaults.string(forKey: Self.authUserIDDefaultsKey)),
      let ownerUserId = Self.normalizedDefaultsString(defaults.string(forKey: Self.mcpKeyOwnerDefaultsKey)),
      ownerUserId == userId
    else {
      return false
    }
    return Self.normalizedDefaultsString(defaults.string(forKey: Self.mcpKeyDefaultsKey)) != nil
  }

  func storedMCPKey() -> String? {
    guard
      let userId = currentAuthUserId(),
      let ownerUserId = Self.normalizedDefaultsString(defaults.string(forKey: Self.mcpKeyOwnerDefaultsKey)),
      ownerUserId == userId
    else {
      return nil
    }
    return Self.normalizedDefaultsString(defaults.string(forKey: Self.mcpKeyDefaultsKey))
  }

  /// Returns the cached MCP key, minting a fresh one via the backend on first use.
  func ensureMCPKey() async throws -> String {
    if let existing = storedMCPKey() {
      return existing
    }
    let ownerUserId = try requireCurrentAuthUserId()
    if let inFlight = mcpKeyWarmTask {
      if inFlight.ownerUserId == ownerUserId {
        return try await finishMCPKeyTask(inFlight.task, id: inFlight.id, ownerUserId: ownerUserId)
      }
      inFlight.task.cancel()
      mcpKeyWarmTask = nil
    }

    let task = Task<String, Error> {
      try await APIClient.shared.createMCPKey(name: "Omi Desktop")
    }
    let id = UUID()
    mcpKeyWarmTask = (ownerUserId, id, task)
    return try await finishMCPKeyTask(task, id: id, ownerUserId: ownerUserId)
  }

  /// Returns the key for a user-triggered local connector setup. Uses an
  /// existing cached key or in-flight warmup first, and mints only when warmup
  /// did not prepare a key in time.
  func mcpKeyForLocalConnectorSetup() async throws -> String {
    if let existing = storedMCPKey() {
      return existing
    }
    let ownerUserId = try requireCurrentAuthUserId()
    if let inFlight = mcpKeyWarmTask, inFlight.ownerUserId == ownerUserId {
      return try await finishMCPKeyTask(inFlight.task, id: inFlight.id, ownerUserId: ownerUserId)
    }
    return try await ensureMCPKey()
  }

  func warmMCPKeyForCurrentUser() async {
    do {
      _ = try await ensureMCPKey()
      log("MemoryExportService: hosted MCP key ready for current user")
    } catch {
      log("MemoryExportService: hosted MCP key warmup failed: \(error.localizedDescription)")
    }
  }

  /// Mint a fresh hosted MCP key and make future setup prompts use it.
  func createNewMCPKey() async throws -> String {
    let ownerUserId = try requireCurrentAuthUserId()
    mcpKeyWarmTask?.task.cancel()
    mcpKeyWarmTask = nil
    let key = try await APIClient.shared.createMCPKey(name: "Omi Desktop")
    storeMCPKey(key, ownerUserId: ownerUserId)
    return key
  }

  private func finishMCPKeyTask(
    _ task: Task<String, Error>,
    id: UUID,
    ownerUserId: String
  ) async throws -> String {
    do {
      let key = try await task.value
      guard currentAuthUserId() == ownerUserId else {
        throw MemoryExportError.requestFailed(
          "Signed-in Omi account changed while preparing the connection key.")
      }
      storeMCPKey(key, ownerUserId: ownerUserId)
      if mcpKeyWarmTask?.id == id {
        mcpKeyWarmTask = nil
      }
      return key
    } catch {
      if mcpKeyWarmTask?.id == id {
        mcpKeyWarmTask = nil
      }
      throw error
    }
  }

  private func storeMCPKey(_ key: String, ownerUserId: String) {
    defaults.set(key, forKey: Self.mcpKeyDefaultsKey)
    defaults.set(ownerUserId, forKey: Self.mcpKeyOwnerDefaultsKey)
    defaults.set(Date().timeIntervalSince1970, forKey: Self.mcpKeyCreatedAtDefaultsKey)
  }

  private func requireCurrentAuthUserId() throws -> String {
    guard let userId = currentAuthUserId() else {
      throw MemoryExportError.requestFailed("Sign in to Omi before creating a connection key.")
    }
    return userId
  }

  private func currentAuthUserId() -> String? {
    Self.normalizedDefaultsString(defaults.string(forKey: Self.authUserIDDefaultsKey))
  }

  private nonisolated static func normalizedDefaultsString(_ value: String?) -> String? {
    let trimmed = (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }

  func testAgentConnections(hostedKey: String, localToken: String) async throws
    -> AgentConnectionTestResult
  {
    async let hostedCount = testHostedMCPMemoryCount(key: hostedKey)
    async let localCount = testLocalAgentToolCount(token: localToken)
    let result = try await AgentConnectionTestResult(
      hostedMemoryCount: hostedCount,
      localToolCount: localCount
    )
    markConnected(.agents)
    return result
  }

  func markConnected(_ destination: MemoryExportDestination) {
    defaults.set(Date().timeIntervalSince1970, forKey: destination.connectedAtKey)
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
      throw MemoryExportError.requestFailed(
        "Local Omi Desktop returned HTTP \(httpResponse.statusCode).")
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

    - Hosted MCP: list available tools before use. If `get_user_profile` exists, use it for a high-level summary. If it is absent or returns `profile: null`, use `get_memories(limit=5)` and `search_memories`.
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
    Config-file MCP clients should prefer `mcp-remote` with the endpoint and Authorization header above.

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
    - If hosted `get_user_profile` exists, call it. If it is absent or returns `profile: null`, call `get_memories` with `limit: 5`.
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
