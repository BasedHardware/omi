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

  /// MCP data serving follows the selected Python serving plane, but OAuth grant
  /// issuance and readback belong to the production identity authority for every
  /// production-family app (including Beta).
  static var mcpOAuthBaseURL: String {
    DesktopBackendEnvironment.authBaseURL()
  }

  static func mcpServerURL(
    bundleIdentifier: String,
    environmentValue: String? = nil
  ) -> String {
    let useDevelopmentBackends = DesktopBackendEnvironment.shouldUseDevelopmentBackends(
      bundleIdentifier: bundleIdentifier,
      updateChannel: AppBuild.currentUpdateChannel
    )
    return DesktopBackendEnvironment.pythonBaseURL(
      useDevelopmentBackends: useDevelopmentBackends,
      bundleIdentifier: bundleIdentifier,
      environmentValue: environmentValue
    ) + mcpEndpointPath
  }

  static func mcpAuthorizeURL(
    bundleIdentifier: String,
    environmentValue: String? = nil
  ) -> String {
    let useDevelopmentBackends = DesktopBackendEnvironment.shouldUseDevelopmentBackends(
      bundleIdentifier: bundleIdentifier,
      updateChannel: AppBuild.currentUpdateChannel
    )
    return DesktopBackendEnvironment.authBaseURL(
      useDevelopmentBackends: useDevelopmentBackends,
      bundleIdentifier: bundleIdentifier,
      environmentValue: environmentValue
    ) + "authorize"
  }

  static func mcpTokenURL(
    bundleIdentifier: String,
    environmentValue: String? = nil
  ) -> String {
    let useDevelopmentBackends = DesktopBackendEnvironment.shouldUseDevelopmentBackends(
      bundleIdentifier: bundleIdentifier,
      updateChannel: AppBuild.currentUpdateChannel
    )
    return DesktopBackendEnvironment.authBaseURL(
      useDevelopmentBackends: useDevelopmentBackends,
      bundleIdentifier: bundleIdentifier,
      environmentValue: environmentValue
    ) + "token"
  }

  /// Canonical hosted MCP path (Streamable HTTP); the backend keeps `/v1/mcp/sse`
  /// as a permanent compatibility alias but clients target `/v1/mcp`.
  static let mcpEndpointPath = "v1/mcp"

  /// The canonical hosted Omi MCP endpoint every client connects to.
  static var mcpServerURL: String { "\(mcpBaseURL)\(mcpEndpointPath)" }

  /// Legacy SSE alias the backend keeps serving and that older client configs
  /// already contain; detection surfaces it as "needs update", never connected.
  static var mcpLegacyServerURL: String { "\(mcpBaseURL)v1/mcp/sse" }

  /// OAuth endpoints exposed by the same backend for MCP custom-connector setup.
  static var mcpAuthorizeURL: String { "\(mcpOAuthBaseURL)authorize" }
  static var mcpTokenURL: String { "\(mcpOAuthBaseURL)token" }

  /// Registered OAuth client for ChatGPT custom connectors on this backend.
  /// Prod registers `omi-chatgpt-prod` as a PUBLIC PKCE client — the token
  /// endpoint rejects any client secret for it, so setup must leave the
  /// secret blank. Dev registers `omi-chatgpt-dev`.
  static var chatgptOAuthClientID: String {
    chatgptOAuthClientID(forOAuthBaseURL: mcpOAuthBaseURL)
  }

  static func chatgptOAuthClientID(forOAuthBaseURL baseURL: String) -> String {
    URL(string: baseURL)?.host == "api.omi.me" ? "omi-chatgpt-prod" : "omi-chatgpt-dev"
  }

  /// The approved ChatGPT directory listing. This is the primary ChatGPT
  /// connection path; the custom-connector flow remains an advanced fallback.
  static let chatGPTDirectoryInstallURL = URL(
    string: "https://chatgpt.com/plugins/plugin_asdk_app_6a1490df4c588191b9339ae21978c873?q=omi")!

  var cloudOAuthClientID: String? {
    switch self {
    case .chatgpt: return Self.chatgptOAuthClientID
    case .claude: return "omi-claude-prod"
    case .notion, .obsidian, .gemini, .agents, .claudeCode, .codex, .openclaw, .hermes:
      return nil
    }
  }

  /// Client IDs that count as "authorized" when scanning OAuth grants — NOT the
  /// same as `cloudOAuthClientID` (the setup form's per-backend value). The
  /// ChatGPT directory is one global plugin that always grants under
  /// `omi-chatgpt-prod`, even on a dev-backend build, so verification must accept
  /// it or ChatGPT never connects on Beta. Mirrors backend `PUBLIC_CHATGPT_CLIENT_IDS`.
  var cloudOAuthGrantClientIDs: Set<String> {
    switch self {
    case .chatgpt: return ["omi-chatgpt-prod", "omi-chatgpt-dev"]
    case .claude: return ["omi-claude-prod"]
    case .notion, .obsidian, .gemini, .agents, .claudeCode, .codex, .openclaw, .hermes:
      return []
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
    case .notion: return "Live page in your workspace"
    case .obsidian: return "Choose once, refresh anytime"
    case .chatgpt: return "Use your Omi context in every chat"
    case .claude: return "Use your Omi context in every chat"
    case .gemini: return "Prompt + memory pack"
    case .agents: return "One prompt for your agent"
    case .claudeCode: return "MCP + context skill"
    case .codex: return "MCP + context skill"
    case .openclaw: return "Memory bank for OpenClaw"
    case .hermes: return "Memory bank for Hermes"
    }
  }

  var description: String {
    switch self {
    case .notion: return "Connect once and Omi keeps an Omi Memories page fresh in your workspace."
    case .obsidian: return "Write Omi memories into your Obsidian vault."
    case .chatgpt:
      return
        "Add Omi in ChatGPT once, then retrieve memories, conversations, people, commitments, and screen history with source evidence."
    case .claude:
      return "Connect over MCP so Claude can retrieve your Omi context live with source evidence."
    case .gemini: return "Copy the prompt and memory pack, then open Gemini."
    case .agents: return "Give your agent one prompt that connects Omi memories and this Mac."
    case .claudeCode:
      return "Connect Omi MCP and install a skill that teaches Claude Code when to retrieve your context."
    case .codex:
      return "Connect Omi MCP and install a skill that teaches Codex when to retrieve your context."
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

  /// How the primary connection button performs setup.
  /// - `.directoryApp`: opens an approved provider directory listing. Provider
  ///   consent completes the connection, then Omi refreshes the OAuth grant.
  /// - `.localAutonomous`: deterministic local CLI/config/file work.
  /// - `.browserAutonomous`: open the cloud connector in the user's default
  ///   signed-in browser and use native macOS automation, with assisted fallback
  ///   on blockers. Currently unmapped: ChatGPT/Claude moved to `.assisted`
  ///   because cross-browser AX automation is too brittle — see
  ///   docs/cloud-connectors-roadmap.md before mapping anything back here.
  /// - `.assisted`: deterministic open + copy, with an on-screen guidance card
  ///   for cloud connectors. The user performs the final paste/click.
  enum MCPExecuteKind: Equatable { case directoryApp, localAutonomous, browserAutonomous, assisted }
  var mcpExecuteKind: MCPExecuteKind {
    switch self {
    case .chatgpt: return .directoryApp
    case .claudeCode, .codex, .openclaw, .hermes: return .localAutonomous
    case .claude, .notion, .obsidian, .gemini, .agents: return .assisted
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

  var directoryInstallURL: URL? {
    self == .chatgpt ? Self.chatGPTDirectoryInstallURL : nil
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
    case .chatgpt:
      return MCPSetupCompletionSummary(
        title: "Authorized in ChatGPT",
        subtitle: "ChatGPT can now use your Omi memories."
      )
    case .claude:
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
      return nil
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

  var notionTokenKey: String { "memoryExportNotionToken" }
  var notionParentPageKey: String { "memoryExportNotionParentPageID" }
  var obsidianVaultPathKey: String { "memoryExportObsidianVaultPath" }
  var exportedCountKey: String { "memoryExportExportedCount.\(rawValue)" }
  var lastExportedAtKey: String { "memoryExportLastExportedAt.\(rawValue)" }
  var detailKey: String { "memoryExportDetail.\(rawValue)" }
  var lastExportPathKey: String { "memoryExportLastExportPath.\(rawValue)" }
  var connectedAtKey: String { "memoryExportConnectedAt.\(rawValue)" }
}
