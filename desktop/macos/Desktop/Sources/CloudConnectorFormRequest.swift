import Foundation

// Argument checks and pure page/form checks for fill_cloud_connector_form.
// The tool fills a connector form without an approval card, so everything here
// runs before any UI step and decides what the UI steps may touch.
extension CloudConnectorFormAutomation {
  struct FieldValue: Equatable {
    let label: String
    let value: String
    let optional: Bool
    let aliases: [String]
  }

  /// Omi's own hosted MCP and OAuth endpoints for this build. The tool fills a
  /// connector form without an approval card, so these are the only URLs it
  /// will ever type into one.
  struct OmiConnectorEndpoints: Equatable, Sendable {
    let serverURL: String
    let authorizeURL: String
    let tokenURL: String

    static var current: OmiConnectorEndpoints {
      OmiConnectorEndpoints(
        serverURL: MemoryExportDestination.mcpServerURL,
        authorizeURL: MemoryExportDestination.mcpAuthorizeURL,
        tokenURL: MemoryExportDestination.mcpTokenURL)
    }
  }

  /// A validated request, ready for the UI steps. Every URL in `values` is the
  /// pinned Omi endpoint, never the caller's spelling of it.
  struct PreparedFill: Equatable {
    let provider: String
    let values: [FieldValue]
    let submit: Bool
  }

  enum PrepareOutcome: Equatable {
    case ready(PreparedFill)
    case refused(String)
  }

  /// Stable codes for arguments refused before any UI is touched.
  enum EndpointRefusal: String, Equatable {
    case serverURLNotOmi = "server_url_not_omi"
    case authURLNotOmi = "auth_url_not_omi"
    case tokenURLNotOmi = "token_url_not_omi"
  }

  nonisolated static func prepareFill(
    _ args: [String: Any],
    endpoints: OmiConnectorEndpoints
  ) -> PrepareOutcome {
    let provider = ((args["provider"] as? String) ?? "").lowercased()
    guard provider == "claude" || provider == "chatgpt" else {
      return .refused("Error: provider must be 'claude' or 'chatgpt'.")
    }

    guard let requestedServerURL = nonEmptyString(args["server_url"]) else {
      return .refused("Error: server_url is required.")
    }
    let requestedAuthURL = nonEmptyString(args["auth_url"])
    let requestedTokenURL = nonEmptyString(args["token_url"])
    if let refusal = endpointRefusal(
      serverURL: requestedServerURL,
      authURL: requestedAuthURL,
      tokenURL: requestedTokenURL,
      endpoints: endpoints)
    {
      return .refused(refusalMessage(refusal, endpoints: endpoints))
    }
    // Type the pinned spelling, so an equivalent variant (case, default port)
    // never reaches the form.
    let serverURL = endpoints.serverURL

    let connectorName = nonEmptyString(args["name"]) ?? "Omi Memory"
    let clientID = nonEmptyString(args["oauth_client_id"]) ?? defaultOAuthClientID(for: provider)
    let clientSecret = nonEmptyString(args["oauth_client_secret"])
    let submit = (args["submit"] as? Bool) ?? false

    var values = [
      FieldValue(
        label: "Name",
        value: connectorName,
        optional: false,
        aliases: ["name", "connector name", "app name"]),
      FieldValue(
        label: "Remote MCP server URL",
        value: serverURL,
        optional: false,
        aliases: ["remote mcp server url", "mcp server url", "server url", "url"]),
      FieldValue(
        label: "OAuth Client ID",
        value: clientID,
        optional: provider == "chatgpt",
        aliases: ["oauth client id", "client id"]),
    ]

    if let clientSecret {
      values.append(
        FieldValue(
          label: "OAuth Client Secret",
          value: clientSecret,
          optional: provider == "chatgpt",
          aliases: ["oauth client secret", "client secret"]))
    }

    if provider == "chatgpt" {
      values.append(contentsOf: [
        FieldValue(
          label: "Authentication",
          value: nonEmptyString(args["authentication"]) ?? "OAuth",
          optional: true,
          aliases: ["authentication", "auth type"]),
        FieldValue(
          label: "Token auth method",
          value:
            nonEmptyString(args["token_auth_method"])
            ?? (clientSecret == nil ? "none" : "client_secret_post"),
          optional: true,
          aliases: ["token auth method", "token authentication method"]),
      ])
      if requestedAuthURL != nil {
        values.append(
          FieldValue(
            label: "Auth URL",
            value: endpoints.authorizeURL,
            optional: true,
            aliases: ["auth url", "authorization url", "authorize url"]))
      }
      if requestedTokenURL != nil {
        values.append(
          FieldValue(
            label: "Token URL",
            value: endpoints.tokenURL,
            optional: true,
            aliases: ["token url"]))
      }
    }

    return .ready(PreparedFill(provider: provider, values: values, submit: submit))
  }

  nonisolated static func endpointRefusal(
    serverURL: String,
    authURL: String?,
    tokenURL: String?,
    endpoints: OmiConnectorEndpoints
  ) -> EndpointRefusal? {
    guard isSameHTTPSEndpoint(serverURL, as: endpoints.serverURL) else {
      return .serverURLNotOmi
    }
    if let authURL, !isSameHTTPSEndpoint(authURL, as: endpoints.authorizeURL) {
      return .authURLNotOmi
    }
    if let tokenURL, !isSameHTTPSEndpoint(tokenURL, as: endpoints.tokenURL) {
      return .tokenURLNotOmi
    }
    return nil
  }

  /// True only when `candidate` names exactly `expected`: https on both sides,
  /// the same host and port, the same path, and no user info, query or
  /// fragment. No prefix or substring match.
  nonisolated static func isSameHTTPSEndpoint(_ candidate: String, as expected: String) -> Bool {
    guard let actual = URLComponents(string: candidate),
      let pinned = URLComponents(string: expected),
      actual.scheme?.lowercased() == "https",
      pinned.scheme?.lowercased() == "https",
      let actualHost = actual.host?.lowercased(), !actualHost.isEmpty,
      actualHost == pinned.host?.lowercased(),
      actual.user == nil, actual.password == nil,
      actual.query == nil, actual.fragment == nil,
      (actual.port ?? 443) == (pinned.port ?? 443)
    else { return false }
    return actual.percentEncodedPath == pinned.percentEncodedPath
  }

  nonisolated private static func refusalMessage(
    _ refusal: EndpointRefusal,
    endpoints: OmiConnectorEndpoints
  ) -> String {
    let field: String
    let expected: String
    switch refusal {
    case .serverURLNotOmi:
      field = "server_url"
      expected = endpoints.serverURL
    case .authURLNotOmi:
      field = "auth_url"
      expected = endpoints.authorizeURL
    case .tokenURLNotOmi:
      field = "token_url"
      expected = endpoints.tokenURL
    }
    return
      "Error: \(refusal.rawValue): this tool only enters Omi's own endpoints, so \(field) must be \(expected). Nothing was typed."
  }

  nonisolated private static func nonEmptyString(_ value: Any?) -> String? {
    guard let string = value as? String else { return nil }
    let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }

  nonisolated private static func defaultOAuthClientID(for provider: String) -> String {
    switch provider {
    case "chatgpt": return MemoryExportDestination.chatgpt.cloudOAuthClientID ?? ""
    case "claude": return MemoryExportDestination.claude.cloudOAuthClientID ?? ""
    default: return ""
    }
  }

  static let chatGPTFormNotVerifiedResult =
    "Error: chatgpt_connector_form_not_verified: Could not find a visible ChatGPT connector form on chatgpt.com in a supported browser. Open ChatGPT's connector settings and its create app form in the signed-in browser, then call this tool again."

  /// True when the text holds a chatgpt.com connector settings URL, as the
  /// address bar shows it (with or without https://). The host must be exactly
  /// chatgpt.com, so a look-alike host or a path that merely mentions it fails.
  nonisolated static func showsChatGPTConnectorSettingsURL(_ text: String) -> Bool {
    text.lowercased()
      .split(whereSeparator: { $0.isWhitespace })
      .contains { token in
        var rest = Substring(token)
        if rest.hasPrefix("https://") {
          rest = rest.dropFirst("https://".count)
        }
        guard rest.hasPrefix("chatgpt.com/") else { return false }
        let route = rest.dropFirst("chatgpt.com/".count)
        return route.hasPrefix("#settings/connectors") || route.hasPrefix("#settings/apps")
      }
  }

  nonisolated static func looksLikeChatGPTConnectorForm(_ text: String) -> Bool {
    let text = text.lowercased()
    return text.contains("server url") || text.contains("connector url")
  }

  /// Exact labels of the connector form's own submit button.
  nonisolated static let chatGPTSubmitButtonLabels: Set<String> = [
    "add", "create", "add app", "create app", "add connector", "create connector",
  ]

  /// The index of the one button whose whole label is the form's Add/Create
  /// label, or nil when there is none or more than one.
  nonisolated static func chatGPTSubmitButtonIndex(labels: [String]) -> Int? {
    let matches = labels.indices.filter { index in
      chatGPTSubmitButtonLabels.contains(
        labels[index].trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }
    return matches.count == 1 ? matches[0] : nil
  }
}
