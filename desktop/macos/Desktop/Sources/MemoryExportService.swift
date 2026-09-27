import AppKit
import Foundation
import OmiSupport

actor MemoryExportService {
  static let shared = MemoryExportService()

  private static let authUserIDDefaultsKey = "auth_userId"
  private static let mcpKeyDefaultsKey = "memoryExportMCPApiKey"
  private static let mcpKeyOwnerDefaultsKey = "memoryExportMCPApiKeyOwnerUserId"
  private static let mcpKeyCreatedAtDefaultsKey = "memoryExportMCPApiKeyCreatedAt"

  private let defaults: UserDefaults
  private let apiClient: APIClient
  private let notionVersion = "2026-03-11"
  private let notionBaseURL = URL(string: "https://api.notion.com/v1")!
  private var mcpKeyWarmTask: (ownerUserId: String, id: UUID, task: Task<String, Error>)?

  init(apiClient: APIClient = .shared, defaults: UserDefaults = .standard) {
    self.apiClient = apiClient
    self.defaults = defaults
  }

  private struct OAuthGrant: Decodable {
    let id: String?
    let clientID: String
    let status: String?
    let revokedAt: String?

    enum CodingKeys: String, CodingKey {
      case id
      case clientID = "client_id"
      case status
      case revokedAt = "revoked_at"
    }

    var isActive: Bool {
      revokedAt == nil && status != "revoked"
    }
  }

  private struct OAuthGrantsResponse: Decodable {
    let grants: [OAuthGrant]
  }

  func status(for destination: MemoryExportDestination) -> MemoryExportStatus {
    let currentMCPKey = storedMCPKey()
    var localMCPStates: [MemoryExportDestination: MemoryExportConnectionDetector.ConnectionState] = [:]
    if destination.supportsMCP,
      let state = MemoryExportConnectionDetector.localMCPConnectionState(
        for: destination, matchingKey: currentMCPKey)
    {
      localMCPStates[destination] = state
    }
    return status(
      for: destination,
      localMCPStates: localMCPStates,
      cloudGrantObservation: destination.cloudOAuthGrantClientIDs.isEmpty ? nil : "cached_or_derived")
  }

  private func status(
    for destination: MemoryExportDestination,
    localMCPStates: [MemoryExportDestination: MemoryExportConnectionDetector.ConnectionState],
    cloudGrantObservation: String? = nil
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
    let localMCPState = localMCPStates[destination]
    let hasLocalMCPConnection = localMCPState == .connected
    let hasConnectedTimestamp = defaults.double(forKey: destination.connectedAtKey) > 0
    let hasConnection: Bool
    switch destination {
    case .claudeCode, .codex, .openclaw, .hermes:
      hasConnection = hasLocalMCPConnection
    case .claude:
      hasConnection = exportedCount > 0 || hasConnectedTimestamp || hasLocalMCPConnection
    case .chatgpt:
      // A copied memory pack is not an OAuth authorization. ChatGPT's status
      // is only changed by the provider-backed grant refresh below.
      hasConnection = hasConnectedTimestamp || hasLocalMCPConnection
    case .notion, .obsidian, .gemini, .agents:
      hasConnection = exportedCount > 0 || hasConnectedTimestamp || hasLocalMCPConnection
    }
    if let cloudGrantObservation {
      DesktopDiagnosticsManager.shared.recordStateAuthoritySignal(
        seam: .connectorStatus,
        from: cloudGrantObservation,
        to: hasConnection ? "connected" : "not_connected",
        direction: "cloud_grant_status_inferred",
        subject: destination.rawValue)
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
      isConfigured = destination == .notion ? NotionMCPConnector.shared.isConnected : exportedCount > 0
    }

    return MemoryExportStatus(
      exportedCount: exportedCount,
      lastExportedAt: lastExportedAt,
      detailText: detailText,
      isConfigured: isConfigured,
      hasConnection: hasConnection,
      needsUpdate: localMCPState == .needsUpdate
    )
  }

  func allStatuses() -> [MemoryExportDestination: MemoryExportStatus] {
    let localMCPStates = MemoryExportConnectionDetector.scanLocalMCPConnectionStates(
      matchingKey: storedMCPKey())
    return Dictionary(
      lastWriteWins: MemoryExportDestination.allCases.map { destination in
        (
          destination,
          status(
            for: destination,
            localMCPStates: localMCPStates,
            cloudGrantObservation: destination.cloudOAuthGrantClientIDs.isEmpty ? nil : "cached_or_derived")
        )
      })
  }

  /// Refreshes the authoritative connection state for a cloud OAuth connector
  /// (ChatGPT/Claude) after the user authorizes in the browser — only the backend
  /// grant list knows the truth. Network failures intentionally retain the last
  /// known state rather than presenting an authorization as revoked.
  func refreshCloudGrantConnectionStatus(for destination: MemoryExportDestination) async -> MemoryExportStatus {
    let clientIDs = destination.cloudOAuthGrantClientIDs
    guard !clientIDs.isEmpty else { return status(for: destination) }
    var observation = "authoritative_grant_check"
    do {
      let response: OAuthGrantsResponse = try await apiClient.get(
        "v1/mcp/oauth/grants", customBaseURL: MemoryExportDestination.mcpOAuthBaseURL, includeBYOK: false)
      let isAuthorized = response.grants.contains { clientIDs.contains($0.clientID) && $0.isActive }

      if isAuthorized {
        defaults.set(Date().timeIntervalSince1970, forKey: destination.connectedAtKey)
        defaults.set("Authorized through \(destination.title)", forKey: destination.detailKey)
        // ChatGPT's directory install and Claude's assisted flow never reach
        // `markConnected` — the grant list is the first authoritative signal
        // that they connected, so the nudge history is cleared from here too.
        clearIntegrationNudgeHistory(for: destination)
      } else {
        defaults.removeObject(forKey: destination.connectedAtKey)
        defaults.removeObject(forKey: destination.detailKey)
      }
    } catch {
      log("MemoryExportService: \(destination.title) OAuth grant refresh failed: \(error.localizedDescription)")
      observation = "cached_after_check_failed"
    }

    let localMCPStates = MemoryExportConnectionDetector.scanLocalMCPConnectionStates(
      matchingKey: storedMCPKey())
    return status(
      for: destination,
      localMCPStates: localMCPStates,
      cloudGrantObservation: observation == "authoritative_grant_check" ? nil : observation)
  }

  /// Revokes every active OAuth grant for a cloud connector, then clears the
  /// local cached projection. The local state is only cleared after the server
  /// confirms each revoke so a transient failure cannot falsely report a
  /// disconnect.
  func disconnectCloudOAuthConnection(for destination: MemoryExportDestination) async throws
    -> MemoryExportStatus
  {
    let clientIDs = destination.cloudOAuthGrantClientIDs
    guard !clientIDs.isEmpty else { return status(for: destination) }

    let response: OAuthGrantsResponse = try await apiClient.get(
      "v1/mcp/oauth/grants", customBaseURL: MemoryExportDestination.mcpOAuthBaseURL, includeBYOK: false)
    let activeGrants = response.grants.filter { clientIDs.contains($0.clientID) && $0.isActive }

    for grant in activeGrants {
      guard let grantID = grant.id, !grantID.isEmpty else {
        throw MemoryExportError.requestFailed("Omi could not identify the (destination.title) authorization.")
      }
      let escapedGrantID = grantID.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? grantID
      try await apiClient.delete(
        "v1/mcp/oauth/grants/\(escapedGrantID)",
        customBaseURL: MemoryExportDestination.mcpOAuthBaseURL,
        includeBYOK: false)
    }

    defaults.removeObject(forKey: destination.connectedAtKey)
    defaults.removeObject(forKey: destination.detailKey)
    let localMCPStates = MemoryExportConnectionDetector.scanLocalMCPConnectionStates(
      matchingKey: storedMCPKey())
    return status(
      for: destination,
      localMCPStates: localMCPStates,
      cloudGrantObservation: "authoritative_grant_check")
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
    clearIntegrationNudgeHistory(for: destination)
  }

  /// Clear this integration's nudge history so a later disconnect is allowed to
  /// make the pitch again instead of finding a spent lifetime budget.
  ///
  /// The only guard is that an owner exists on the far side of the hop. Carrying
  /// the connecting owner across would mean comparing a raw `authUserId` default
  /// against `RuntimeOwnerIdentity`, which differ by trimming, the
  /// non-production automation override, and the nil returned mid-transition —
  /// a comparison that misfires on exactly the builds this runs on. The residual
  /// risk is small and self-correcting: the store is itself owner-scoped, so the
  /// worst case is clearing the current owner's history for one integration,
  /// which costs them one extra offer.
  private func clearIntegrationNudgeHistory(for destination: MemoryExportDestination) {
    Task { @MainActor in
      guard RuntimeOwnerIdentity.currentOwnerId() != nil else { return }
      IntegrationNudgeCoordinator.shared.noteConnected(route: .exportDestination(destination.rawValue))
    }
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
    return try Self.parseHostedMCPMemoryCount(data: data, statusCode: httpResponse.statusCode)
  }

  /// Parses a hosted ``tools/call get_memories`` response into a memory count.
  /// Tool failures arrive as ``isError`` results, not JSON-RPC errors — the
  /// real reason lives in ``structuredContent.error.message``, with the
  /// serialized ``{"error": ...}`` text block as the fallback.
  static func parseHostedMCPMemoryCount(data: Data, statusCode: Int) throws -> Int {
    guard (200...299).contains(statusCode) else {
      throw MemoryExportError.requestFailed("Hosted MCP returned HTTP \(statusCode).")
    }

    let rpc = try JSONSerialization.jsonObject(with: data) as? [String: Any]
    if let error = rpc?["error"] as? [String: Any],
      let message = error["message"] as? String
    {
      throw MemoryExportError.requestFailed("Hosted MCP failed: \(message)")
    }
    guard let result = rpc?["result"] as? [String: Any] else {
      throw MemoryExportError.requestFailed("Hosted MCP did not return memory data.")
    }
    let content = result["content"] as? [[String: Any]]
    let text = content?.first?["text"] as? String
    if result["isError"] as? Bool == true {
      throw MemoryExportError.requestFailed(
        "Hosted MCP failed: \(hostedMCPToolErrorMessage(result: result, text: text))")
    }
    guard
      let text,
      let textData = text.data(using: .utf8),
      let payload = try JSONSerialization.jsonObject(with: textData) as? [String: Any],
      let memories = payload["memories"] as? [Any]
    else {
      throw MemoryExportError.requestFailed("Hosted MCP did not return memory data.")
    }

    return memories.count
  }

  /// Hosted MCP tool failures arrive as ``isError`` results, not JSON-RPC
  /// errors — the real reason lives in ``structuredContent.error.message``,
  /// with the serialized ``{"error": ...}`` text block as the fallback.
  static func hostedMCPToolErrorMessage(result: [String: Any], text: String?) -> String {
    if let structured = result["structuredContent"] as? [String: Any],
      let error = structured["error"] as? [String: Any],
      let message = error["message"] as? String
    {
      return message
    }
    if let text,
      let textData = text.data(using: .utf8),
      let parsed = try? JSONSerialization.jsonObject(with: textData) as? [String: Any],
      let error = parsed["error"] as? [String: Any],
      let message = error["message"] as? String
    {
      return message
    }
    return text ?? "Tool call failed."
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
    AgentContextSkillInstaller.document
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

  func fetchMemories(limit: Int) async throws -> [ServerMemory] {
    let pageSize = max(1, min(limit, 500))
    do {
      let remoteMemories: [ServerMemory] = try await Self.fetchAllCursorPages(pageSize: pageSize) {
        pageLimit, cursor in
        try await APIClient.shared.getMemoriesPage(
          limit: pageLimit,
          cursor: cursor,
          includeArchive: true)
      }
      if !remoteMemories.isEmpty {
        return remoteMemories
      }
    } catch {
      log("MemoryExportService: Remote memory fetch failed, falling back to local cache: \(error)")
    }

    let localMemories: [ServerMemory] = try await Self.fetchAllPages(pageSize: pageSize) {
      pageLimit, offset in
      try await MemoryStorage.shared.getLocalMemories(limit: pageLimit, offset: offset)
    }
    if !localMemories.isEmpty {
      return localMemories
    }

    throw MemoryExportError.noMemories
  }

  /// Fetch a complete export without silently treating a UI page size as a
  /// total-account cap. Advancing by the count returned also avoids gaps when a
  /// backend clamps the requested page size.
  static func fetchAllPages<Element>(
    pageSize: Int,
    fetch: (_ limit: Int, _ offset: Int) async throws -> [Element]
  ) async throws -> [Element] {
    let boundedPageSize = max(1, min(pageSize, 500))
    var offset = 0
    var result: [Element] = []
    while true {
      let page = try await fetch(boundedPageSize, offset)
      result.append(contentsOf: page)
      guard page.count == boundedPageSize else { return result }
      offset += page.count
    }
  }

  /// Page a remote memory list until the backend omits ``X-Omi-Memory-Next-Cursor``.
  static func fetchAllCursorPages(
    pageSize: Int,
    fetch: (_ limit: Int, _ cursor: String?) async throws -> APIClient.MemoryListPage
  ) async throws -> [ServerMemory] {
    let boundedPageSize = max(1, min(pageSize, 500))
    var cursor: String? = nil
    var result: [ServerMemory] = []
    var seenCursors = Set<String>()
    while true {
      let page = try await fetch(boundedPageSize, cursor)
      // A truncated page is explicitly incomplete and carries no resumable
      // cursor; an export cannot claim completeness from it.
      if page.truncated {
        throw MemoryExportError.requestFailed(
          "Memory export stopped because the server returned a truncated list.")
      }
      result.append(contentsOf: page.memories)
      guard let nextCursor = page.nextCursor, !nextCursor.isEmpty else {
        return result
      }
      // Fail closed on a repeated continuation token so a buggy backend cannot
      // pin export in an infinite loop.
      if !seenCursors.insert(nextCursor).inserted {
        throw MemoryExportError.requestFailed(
          "Memory export stopped because the server repeated a continuation token.")
      }
      cursor = nextCursor
    }
  }

  func buildMarkdownPack(
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

  func persistStatus(
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
