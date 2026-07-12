import CryptoKit
import Foundation

enum AgentContextRevision {
  static func make(
    source: AgentContextSource,
    payload: [String: Any],
    outcome: AgentContextSourceOutcome
  ) throws -> String {
    let material: [String: Any] = [
      "source": source.rawValue,
      "outcome": outcome.rawValue,
      "payload": payload,
    ]
    guard JSONSerialization.isValidJSONObject(material) else {
      throw BridgeError.agentError("Context source payload is not valid JSON")
    }
    let data = try JSONSerialization.data(withJSONObject: material, options: [.sortedKeys])
    return "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }
}

struct AgentExecutionProfile: Equatable, Sendable {
  enum CredentialScope: String, Sendable {
    case managedCloud = "managed_cloud"
    case localUser = "local_user"
  }

  enum ExecutionRole: String, Sendable {
    case coordinator
    case leaf
  }

  let profileGeneration: Int
  let adapterId: String
  let credentialScope: CredentialScope
  let modelProfile: String?
  let workingDirectory: String
  let executionRole: ExecutionRole

  init?(dictionary: [String: Any]) {
    guard
      let profileGeneration = dictionary["profileGeneration"] as? Int,
      let adapterId = dictionary["adapterId"] as? String,
      let credentialScopeValue = dictionary["credentialScope"] as? String,
      let credentialScope = CredentialScope(rawValue: credentialScopeValue),
      let workingDirectory = dictionary["workingDirectory"] as? String,
      let executionRoleValue = dictionary["executionRole"] as? String,
      let executionRole = ExecutionRole(rawValue: executionRoleValue)
    else { return nil }
    self.profileGeneration = profileGeneration
    self.adapterId = adapterId
    self.credentialScope = credentialScope
    self.modelProfile = dictionary["modelProfile"] as? String
    self.workingDirectory = workingDirectory
    self.executionRole = executionRole
  }
}

enum AgentExecutionProfileLifecycle {
  static let defaultPreferenceAppliesTo = "new_sessions"
  static let defaultPreferenceChangeRequiresDaemonRestart = false
}

struct AgentDefaultExecutionProfile: Equatable, Sendable {
  let preferenceGeneration: Int
  let adapterId: String
  let credentialScope: AgentExecutionProfile.CredentialScope
  let modelProfile: String?
  let workingDirectory: String
  let appliesTo: String

  init?(dictionary: [String: Any]) {
    guard
      let preferenceGeneration = dictionary["preferenceGeneration"] as? Int,
      let adapterId = dictionary["adapterId"] as? String,
      let credentialScopeValue = dictionary["credentialScope"] as? String,
      let credentialScope = AgentExecutionProfile.CredentialScope(rawValue: credentialScopeValue),
      let workingDirectory = dictionary["workingDirectory"] as? String,
      let appliesTo = dictionary["appliesTo"] as? String,
      appliesTo == AgentExecutionProfileLifecycle.defaultPreferenceAppliesTo
    else { return nil }
    self.preferenceGeneration = preferenceGeneration
    self.adapterId = adapterId
    self.credentialScope = credentialScope
    self.modelProfile = dictionary["modelProfile"] as? String
    self.workingDirectory = workingDirectory
    self.appliesTo = appliesTo
  }
}

struct AgentSurfaceSession: Equatable, Sendable {
  let created: Bool
  let conversationId: String
  let sessionId: String
  let profile: AgentExecutionProfile

  init(created: Bool, conversationId: String, sessionId: String, profile: AgentExecutionProfile) {
    self.created = created
    self.conversationId = conversationId
    self.sessionId = sessionId
    self.profile = profile
  }

  init?(dictionary: [String: Any]) {
    guard
      let created = dictionary["created"] as? Bool,
      let conversationId = dictionary["conversationId"] as? String,
      let sessionId = dictionary["sessionId"] as? String,
      let profileDictionary = dictionary["profile"] as? [String: Any],
      let profile = AgentExecutionProfile(dictionary: profileDictionary)
    else { return nil }
    self.created = created
    self.conversationId = conversationId
    self.sessionId = sessionId
    self.profile = profile
  }
}

struct LegacyMainChatSessionAliasEntry: Equatable, Hashable, Sendable {
  let chatId: String
  let agentSessionId: String

  var dictionary: [String: String] {
    ["chatId": chatId, "agentSessionId": agentSessionId]
  }
}

struct LegacyMainChatSessionImportReceipt: Equatable, Sendable {
  let ownerId: String
  let acceptedEntries: [LegacyMainChatSessionAliasEntry]
  let importedCount: Int

  init(
    ownerId: String,
    acceptedEntries: [LegacyMainChatSessionAliasEntry],
    importedCount: Int
  ) {
    self.ownerId = ownerId
    self.acceptedEntries = acceptedEntries
    self.importedCount = importedCount
  }

  init?(dictionary: [String: Any]) {
    guard
      let rawOwnerId = dictionary["ownerId"] as? String,
      !rawOwnerId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      let acceptedCount = dictionary["acceptedCount"] as? Int,
      let importedCount = dictionary["importedCount"] as? Int,
      importedCount >= 0,
      importedCount <= acceptedCount,
      let rawEntries = dictionary["acceptedEntries"] as? [[String: Any]]
    else { return nil }

    let entries = rawEntries.compactMap { raw -> LegacyMainChatSessionAliasEntry? in
      guard
        let rawChatId = raw["chatId"] as? String,
        let rawSessionId = raw["agentSessionId"] as? String
      else { return nil }
      let chatId = rawChatId.trimmingCharacters(in: .whitespacesAndNewlines)
      let agentSessionId = rawSessionId.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !chatId.isEmpty, !agentSessionId.isEmpty else { return nil }
      return LegacyMainChatSessionAliasEntry(chatId: chatId, agentSessionId: agentSessionId)
    }
    guard
      entries.count == rawEntries.count,
      entries.count == acceptedCount,
      Set(entries.map(\.chatId)).count == entries.count
    else { return nil }

    ownerId = rawOwnerId.trimmingCharacters(in: .whitespacesAndNewlines)
    acceptedEntries = entries
    self.importedCount = importedCount
  }
}

enum LegacyMainChatSessionAliasMigration {
  enum Outcome: Equatable, Sendable {
    case noAliases
    case acknowledged(removedCount: Int)
    case retained(reason: String)
  }

  static let owner = "desktop-agent-bridge"
  static let removalCondition =
    "all supported desktop versions have imported UserDefaults main-chat session aliases into omi-agentd"
  static let removeBy = "2026-10-01"
  static let defaultsKey = "mainChatRuntimeSessionIdsByOwnerAndChat"

  private struct PendingAlias: Sendable {
    let defaultsKey: String
    let storedSessionId: String
    let entry: LegacyMainChatSessionAliasEntry
  }

  static func migrate(
    ownerId: String,
    defaults: UserDefaults,
    importer: @Sendable ([LegacyMainChatSessionAliasEntry]) async throws ->
      LegacyMainChatSessionImportReceipt
  ) async -> Outcome {
    let ownerId = ownerId.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !ownerId.isEmpty else { return .retained(reason: "invalid_owner") }
    guard let rawMap = defaults.dictionary(forKey: defaultsKey), !rawMap.isEmpty else {
      return .noAliases
    }
    var map: [String: String] = [:]
    for (key, value) in rawMap {
      guard let sessionId = value as? String else {
        return .retained(reason: "invalid_defaults_payload")
      }
      map[key] = sessionId
    }

    let prefix = "\(ownerId)|"
    var pending: [PendingAlias] = []
    var seenChatIds = Set<String>()
    for key in map.keys.filter({ $0.hasPrefix(prefix) }).sorted() {
      guard let storedSessionId = map[key] else { continue }
      let suffix = String(key.dropFirst(prefix.count))
      let chatId = suffix.isEmpty ? "default" : suffix.trimmingCharacters(in: .whitespacesAndNewlines)
      let agentSessionId = storedSessionId.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !chatId.isEmpty, !agentSessionId.isEmpty, seenChatIds.insert(chatId).inserted else {
        return .retained(reason: "invalid_alias_entry")
      }
      pending.append(PendingAlias(
        defaultsKey: key,
        storedSessionId: storedSessionId,
        entry: LegacyMainChatSessionAliasEntry(chatId: chatId, agentSessionId: agentSessionId)
      ))
    }
    guard !pending.isEmpty else { return .noAliases }

    let entries = pending.map(\.entry)
    let receipt: LegacyMainChatSessionImportReceipt
    do {
      receipt = try await importer(entries)
    } catch {
      return .retained(reason: "kernel_import_failed")
    }
    guard receipt.ownerId == ownerId, receipt.acceptedEntries == entries else {
      return .retained(reason: "invalid_kernel_receipt")
    }

    var latest = defaults.dictionary(forKey: defaultsKey) ?? [:]
    var removedCount = 0
    for alias in pending where latest[alias.defaultsKey] as? String == alias.storedSessionId {
      latest.removeValue(forKey: alias.defaultsKey)
      removedCount += 1
    }
    if latest.isEmpty {
      defaults.removeObject(forKey: defaultsKey)
    } else {
      defaults.set(latest, forKey: defaultsKey)
    }
    return .acknowledged(removedCount: removedCount)
  }
}

struct AgentSessionCreationProfile: Equatable, Sendable {
  let adapterId: String
  let modelProfile: String?
  let workingDirectory: String

  var dictionary: [String: Any] {
    [
      "adapterId": adapterId,
      "modelProfile": modelProfile ?? NSNull(),
      "workingDirectory": workingDirectory,
    ]
  }
}

struct AgentSessionProfileMigration: Equatable, Sendable {
  let sessionId: String
  let previousProfileGeneration: Int
  let profile: AgentExecutionProfile
  let staleBindingIds: [String]

  init?(dictionary: [String: Any]) {
    guard
      let sessionId = dictionary["sessionId"] as? String,
      let previousProfileGeneration = dictionary["previousProfileGeneration"] as? Int,
      let profileDictionary = dictionary["profile"] as? [String: Any],
      let profile = AgentExecutionProfile(dictionary: profileDictionary),
      let staleBindingIds = dictionary["staleBindingIds"] as? [String]
    else { return nil }
    self.sessionId = sessionId
    self.previousProfileGeneration = previousProfileGeneration
    self.profile = profile
    self.staleBindingIds = staleBindingIds
  }
}

enum AgentContextSource: String, CaseIterable, Sendable {
  case identity
  case memories
  case goals
  case tasks
  case screen
  case workspace
  case surface
}

enum AgentContextSourceOutcome: String, Sendable {
  case available
  case empty
  case unavailable
  case redacted
}

struct AgentContextSourceUpdateReceipt: Equatable, Sendable {
  let sessionId: String
  let source: AgentContextSource
  let sourceRevision: String
  let changed: Bool
  let snapshotVersion: String
  let snapshotGeneration: Int
  let rendererFingerprint: String

  init?(dictionary: [String: Any]) {
    guard
      let sessionId = dictionary["sessionId"] as? String,
      let sourceValue = dictionary["source"] as? String,
      let source = AgentContextSource(rawValue: sourceValue),
      let sourceRevision = dictionary["sourceRevision"] as? String,
      let changed = dictionary["changed"] as? Bool,
      let snapshotVersion = dictionary["snapshotVersion"] as? String,
      let snapshotGeneration = dictionary["snapshotGeneration"] as? Int,
      let rendererFingerprint = dictionary["rendererFingerprint"] as? String
    else { return nil }
    self.sessionId = sessionId
    self.source = source
    self.sourceRevision = sourceRevision
    self.changed = changed
    self.snapshotVersion = snapshotVersion
    self.snapshotGeneration = snapshotGeneration
    self.rendererFingerprint = rendererFingerprint
  }
}

struct AgentContextRecentTurn: Equatable, Sendable {
  let turnId: String
  let turnSeq: Int
  let role: String
  let content: String
  let status: String
  let origin: String
  let createdAtMs: Int

  init(
    turnId: String,
    turnSeq: Int,
    role: String,
    content: String,
    status: String,
    origin: String,
    createdAtMs: Int
  ) {
    self.turnId = turnId
    self.turnSeq = turnSeq
    self.role = role
    self.content = content
    self.status = status
    self.origin = origin
    self.createdAtMs = createdAtMs
  }

  init?(dictionary: [String: Any]) {
    guard
      let turnId = dictionary["turnId"] as? String,
      let turnSeq = dictionary["turnSeq"] as? Int,
      let role = dictionary["role"] as? String,
      let content = dictionary["content"] as? String,
      let status = dictionary["status"] as? String,
      let origin = dictionary["origin"] as? String,
      let createdAtMs = dictionary["createdAtMs"] as? Int
    else { return nil }
    self.turnId = turnId
    self.turnSeq = turnSeq
    self.role = role
    self.content = content
    self.status = status
    self.origin = origin
    self.createdAtMs = createdAtMs
  }
}

struct AgentContextSnapshot: @unchecked Sendable {
  let snapshotId: String
  let version: String
  let snapshotGeneration: Int
  let rendererPolicyVersion: String
  let rendererFingerprint: String
  let capabilityVersion: String
  let renderedContext: String
  let ownerId: String
  let sessionId: String
  let conversationId: String
  let recentTurns: [[String: Any]]
  let sourceOutcomes: [[String: Any]]
  let activeRuns: [[String: Any]]
  let capabilities: [String: Any]

  init?(dictionary: [String: Any]) {
    guard
      let snapshotId = dictionary["snapshotId"] as? String,
      let version = dictionary["version"] as? String,
      let snapshotGeneration = dictionary["snapshotGeneration"] as? Int,
      let rendererPolicyVersion = dictionary["rendererPolicyVersion"] as? String,
      let rendererFingerprint = dictionary["rendererFingerprint"] as? String,
      let capabilityVersion = dictionary["capabilityVersion"] as? String,
      let renderedContext = dictionary["renderedContext"] as? String,
      let ownerId = dictionary["ownerId"] as? String,
      let sessionId = dictionary["sessionId"] as? String,
      let conversationId = dictionary["conversationId"] as? String,
      let recentTurns = dictionary["recentTurns"] as? [[String: Any]],
      let sourceOutcomes = dictionary["sourceOutcomes"] as? [[String: Any]],
      let activeRuns = dictionary["activeRuns"] as? [[String: Any]],
      let capabilities = dictionary["capabilities"] as? [String: Any],
      capabilities["executionRole"] as? String != nil,
      capabilities["manifestVersion"] as? Int != nil,
      capabilities["manifestDigest"] as? String != nil,
      capabilities["allowedToolNames"] as? [String] != nil
    else { return nil }
    self.snapshotId = snapshotId
    self.version = version
    self.snapshotGeneration = snapshotGeneration
    self.rendererPolicyVersion = rendererPolicyVersion
    self.rendererFingerprint = rendererFingerprint
    self.capabilityVersion = capabilityVersion
    self.renderedContext = renderedContext
    self.ownerId = ownerId
    self.sessionId = sessionId
    self.conversationId = conversationId
    self.recentTurns = recentTurns
    self.sourceOutcomes = sourceOutcomes
    self.activeRuns = activeRuns
    self.capabilities = capabilities
  }

  var freshness: AgentContextFreshness {
    AgentContextFreshness(version: version, generation: snapshotGeneration)
  }

  func sourceRevision(for source: AgentContextSource) -> String? {
    sourceOutcomes.first(where: { $0["source"] as? String == source.rawValue })?["sourceRevision"] as? String
  }

  var typedRecentTurns: [AgentContextRecentTurn] {
    recentTurns.compactMap(AgentContextRecentTurn.init(dictionary:))
  }
}

struct AgentQueryAttachment: Equatable, Sendable {
  let attachmentId: String
  let displayName: String
  let mimeType: String
  let sizeBytes: Int?
  let uri: String?

  var dictionary: [String: Any] {
    var value: [String: Any] = [
      "attachmentId": attachmentId,
      "displayName": displayName,
      "mimeType": mimeType,
    ]
    if let sizeBytes { value["sizeBytes"] = sizeBytes }
    if let uri { value["uri"] = uri }
    return value
  }
}

struct AgentContextFreshness: Equatable, Sendable {
  let version: String
  let generation: Int
}

/// Lightweight client handle for the shared Node.js agent runtime.
actor AgentBridge {

  struct QueryResult {
    let text: String
    let costUsd: Double
    let omiSessionId: String
    let runId: String
    let attemptId: String
    let adapterSessionId: String?
    let terminalStatus: String
    let inputTokens: Int
    let outputTokens: Int
    let cacheReadTokens: Int
    let cacheWriteTokens: Int
    let artifacts: [AgentArtifactProjection]
    let completionDeltaArtifacts: [AgentArtifactProjection]

    init(
      text: String,
      costUsd: Double,
      omiSessionId: String,
      runId: String,
      attemptId: String,
      adapterSessionId: String?,
      terminalStatus: String,
      inputTokens: Int,
      outputTokens: Int,
      cacheReadTokens: Int,
      cacheWriteTokens: Int,
      artifacts: [AgentArtifactProjection] = [],
      completionDeltaArtifacts: [AgentArtifactProjection] = []
    ) {
      self.text = text
      self.costUsd = costUsd
      self.omiSessionId = omiSessionId
      self.runId = runId
      self.attemptId = attemptId
      self.adapterSessionId = adapterSessionId
      self.terminalStatus = terminalStatus
      self.inputTokens = inputTokens
      self.outputTokens = outputTokens
      self.cacheReadTokens = cacheReadTokens
      self.cacheWriteTokens = cacheWriteTokens
      self.artifacts = artifacts
      self.completionDeltaArtifacts = completionDeltaArtifacts
    }
  }

  typealias TextDeltaHandler = @Sendable (String) -> Void
  typealias ToolCallHandler = @Sendable (String, String, [String: Any]) async -> String
  typealias ToolActivityHandler = @Sendable (String, String, String?, [String: Any]?) -> Void
  typealias ThinkingDeltaHandler = @Sendable (String) -> Void
  typealias ToolResultDisplayHandler = @Sendable (String, String, String) -> Void
  typealias AuthRequiredHandler = @Sendable ([[String: Any]], String?) -> Void
  typealias AuthSuccessHandler = @Sendable () -> Void

  private final class BridgeOutputTracker: @unchecked Sendable {
    private let lock = NSLock()
    private var _hasOutput = false

    var hasOutput: Bool {
      lock.lock()
      defer { lock.unlock() }
      return _hasOutput
    }

    func markOutput() {
      lock.lock()
      _hasOutput = true
      lock.unlock()
    }
  }

  let harnessMode: String

  private let clientId = UUID().uuidString
  private let runtime: AgentRuntimeProcess
  private var registered = false
  private var activeRequestId: String?
  private var lastKnownQuota: APIClient.ChatUsageQuota?
  private var tokenRefreshTask: Task<Void, Never>?

  var isAlive: Bool {
    get async {
      await runtime.isAlive
    }
  }

  init(harnessMode: String = "piMono", runtime: AgentRuntimeProcess = .shared) {
    self.harnessMode = harnessMode
    self.runtime = runtime
  }

  private var isPiMonoHarness: Bool {
    AgentRuntimeProcess.adapterId(forHarnessMode: harnessMode) == AgentAdapterId.piMono.rawValue
  }

  func setGlobalAuthHandlers(
    onAuthRequired: AuthRequiredHandler?,
    onAuthSuccess: AuthSuccessHandler?
  ) async {
    await runtime.setGlobalAuthHandlers(
      clientId: clientId,
      onAuthRequired: onAuthRequired,
      onAuthSuccess: onAuthSuccess
    )
  }

  func start() async throws {
    guard !registered else { return }
    try await runtime.registerClient(clientId: clientId, harnessMode: harnessMode)
    registered = true
    await migrateLegacyMainChatSessionsIfNeeded()

    if isPiMonoHarness {
      ensureTokenRefreshTask()
      _ = try? await refreshAuthToken()
    }
  }

  func restart() async throws {
    try await runtime.restart(harnessMode: harnessMode)
    registered = true
  }

  /// Reset client registration after an unexpected process exit so `restart()`/`start()`
  /// can spawn a fresh Node bridge (the process is already gone).
  func prepareForCrashRecovery() {
    tokenRefreshTask?.cancel()
    tokenRefreshTask = nil
    registered = false
    activeRequestId = nil
    lastKnownQuota = nil
  }

  func stopAndWaitForExit() async {
    tokenRefreshTask?.cancel()
    tokenRefreshTask = nil
    let wasRegistered = registered
    registered = false
    activeRequestId = nil
    lastKnownQuota = nil
    guard wasRegistered else { return }
    await runtime.unregisterClient(clientId: clientId)
  }

  func stop() {
    tokenRefreshTask?.cancel()
    tokenRefreshTask = nil
    let wasRegistered = registered
    registered = false
    activeRequestId = nil
    lastKnownQuota = nil
    guard wasRegistered else { return }
    Task {
      await runtime.unregisterClient(clientId: clientId)
    }
  }

  func authenticate(methodId: String) {
    Task {
      await runtime.authenticate(methodId: methodId)
    }
  }

  func configureDefaultExecutionProfile(
    adapterId: String,
    modelProfile: String?,
    workingDirectory: String,
    expectedPreferenceGeneration: Int? = nil
  ) async throws -> AgentDefaultExecutionProfile {
    try await start()
    if adapterId == AgentAdapterId.piMono.rawValue {
      ensureTokenRefreshTask()
      _ = try? await refreshAuthToken()
    }
    return try await runtime.configureDefaultExecutionProfile(
      clientId: clientId,
      adapterId: adapterId,
      modelProfile: modelProfile,
      workingDirectory: workingDirectory,
      expectedPreferenceGeneration: expectedPreferenceGeneration
    )
  }

  func resolveSurfaceSession(
    _ surface: AgentSurfaceReference,
    title: String? = nil,
    creationProfile: AgentSessionCreationProfile? = nil
  ) async throws -> AgentSurfaceSession {
    try await start()
    return try await runtime.resolveSurfaceSession(
      clientId: clientId,
      surface: surface,
      title: title,
      creationProfile: creationProfile
    )
  }

  func migrateSessionExecutionProfile(
    sessionId: String,
    expectedProfileGeneration: Int,
    adapterId: String,
    modelProfile: String?,
    workingDirectory: String
  ) async throws -> AgentSessionProfileMigration {
    try await start()
    return try await runtime.migrateSessionExecutionProfile(
      clientId: clientId,
      sessionId: sessionId,
      expectedProfileGeneration: expectedProfileGeneration,
      adapterId: adapterId,
      modelProfile: modelProfile,
      workingDirectory: workingDirectory
    )
  }

  func warmupSession(_ session: AgentSurfaceSession) async {
    await runtime.warmupSession(
      clientId: clientId,
      sessionId: session.sessionId,
      profileGeneration: session.profile.profileGeneration
    )
  }

  func updateContextSource(
    sessionId: String,
    surfaceKind: String,
    source: AgentContextSource,
    sourceRevision: String,
    outcome: AgentContextSourceOutcome,
    capturedAtMs: Int,
    expiresAtMs: Int? = nil,
    payload: [String: Any]
  ) async throws -> AgentContextSourceUpdateReceipt {
    try await start()
    return try await runtime.updateContextSource(
      clientId: clientId,
      sessionId: sessionId,
      surfaceKind: surfaceKind,
      source: source,
      sourceRevision: sourceRevision,
      outcome: outcome,
      capturedAtMs: capturedAtMs,
      expiresAtMs: expiresAtMs,
      payload: payload
    )
  }

  func getContextSnapshot(sessionId: String, surfaceKind: String) async throws -> AgentContextSnapshot {
    try await start()
    return try await runtime.getContextSnapshot(
      clientId: clientId,
      sessionId: sessionId,
      surfaceKind: surfaceKind)
  }

  func invalidateSurface(_ surface: AgentSurfaceReference) async {
    await runtime.invalidateSurface(clientId: clientId, surface: surface)
  }

  func clearOwnerState() async {
    await runtime.clearOwnerState(clientId: clientId)
  }

  func importLegacyMainChatSessions(
    _ entries: [LegacyMainChatSessionAliasEntry]
  ) async throws -> LegacyMainChatSessionImportReceipt {
    try await runtime.importLegacyMainChatSessions(clientId: clientId, entries: entries)
  }

  func recordJournalTurn(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    turn: KernelJournalTurnWrite
  ) async throws -> KernelJournalTurn {
    try await runtime.recordJournalTurn(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      turn: turn
    )
  }

  func updateJournalTurn(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    update: KernelJournalTurnUpdate
  ) async throws -> KernelJournalTurn {
    try await runtime.updateJournalTurn(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      update: update
    )
  }

  func listJournalTurns(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    afterTurnSeq: Int = 0,
    limit: Int = 100
  ) async throws -> AgentRuntimeProcess.JournalOperationResult {
    try await runtime.listJournalTurns(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      afterTurnSeq: afterTurnSeq,
      limit: limit
    )
  }

  func importRemoteJournalTurn(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    turn: KernelJournalRemoteTurn
  ) async throws -> KernelJournalTurn {
    try await runtime.importRemoteJournalTurn(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      turn: turn
    )
  }

  func clearJournalTurns(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    expectedGeneration: Int? = nil
  ) async throws -> Int {
    try await runtime.clearJournalTurns(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      expectedGeneration: expectedGeneration
    )
  }

  func setJournalTurnChangedHandler(
    _ handler: @escaping AgentRuntimeProcess.JournalTurnChangedHandler
  ) async {
    await runtime.setJournalTurnChangedHandler(handler)
  }

  func controlTool(name: String, input: [String: Any]) async throws -> String {
    try await start()
    return try await runtime.directControlTool(
      clientId: clientId,
      harnessMode: harnessMode,
      name: name,
      input: input
    )
  }

#if DEBUG
  func debugAutomationControlTool(
    name: String,
    input: [String: Any],
    ownerId: String = "scenario-13-automation-owner"
  ) async throws -> String {
    try await start()
    return try await runtime.debugAutomationControlTool(
      clientId: clientId,
      harnessMode: harnessMode,
      name: name,
      input: input,
      ownerId: ownerId
    )
  }
#endif

  func query(
    prompt: String,
    surface: AgentSurfaceReference,
    mode: String? = nil,
    imageData: Data? = nil,
    attachments: [AgentQueryAttachment] = [],
    expectedContext: AgentContextFreshness? = nil,
    onTextDelta: @escaping TextDeltaHandler,
    onToolActivity: @escaping ToolActivityHandler,
    onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
    onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
    onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
    onAuthSuccess: @escaping AuthSuccessHandler = {}
  ) async throws -> QueryResult {
    let session = try await resolveSurfaceSession(surface)
    return try await query(
      prompt: prompt,
      session: session,
      surface: surface,
      mode: mode,
      imageData: imageData,
      attachments: attachments,
      expectedContext: expectedContext,
      onTextDelta: onTextDelta,
      onToolActivity: onToolActivity,
      onThinkingDelta: onThinkingDelta,
      onToolResultDisplay: onToolResultDisplay,
      onAuthRequired: onAuthRequired,
      onAuthSuccess: onAuthSuccess
    )
  }

  func query(
    prompt: String,
    session: AgentSurfaceSession,
    surface: AgentSurfaceReference,
    mode: String? = nil,
    imageData: Data? = nil,
    attachments: [AgentQueryAttachment] = [],
    expectedContext: AgentContextFreshness? = nil,
    onTextDelta: @escaping TextDeltaHandler,
    onToolActivity: @escaping ToolActivityHandler,
    onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
    onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
    onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
    onAuthSuccess: @escaping AuthSuccessHandler = {}
  ) async throws -> QueryResult {
    await setGlobalAuthHandlers(onAuthRequired: onAuthRequired, onAuthSuccess: onAuthSuccess)
    try await start()

    guard activeRequestId == nil else {
      throw BridgeError.requestAlreadyActive
    }

    let usesManagedCloud = session.profile.credentialScope == .managedCloud
    if usesManagedCloud {
      if let cached = lastKnownQuota, !cached.allowed {
        QueryTracerContext.current?.mark("quota_check", metadata: ["result": "exceeded_cached"])
        throw BridgeError.quotaExceeded(
          plan: cached.plan,
          unit: cached.unit,
          used: cached.used,
          limit: cached.limit,
          resetAtUnix: cached.resetAt
        )
      }
      QueryTracerContext.current?.mark("quota_check", metadata: ["mode": "optimistic"])
      Task { [weak self] in
        if let quota = await APIClient.shared.fetchChatUsageQuota() {
          await self?.cacheQuota(quota)
        }
      }
    }

    let requestId = UUID().uuidString
    activeRequestId = requestId
    defer { activeRequestId = nil }

    let bridgeOutputTracker = BridgeOutputTracker()
    let trackedTextDelta: TextDeltaHandler = { delta in
      if !delta.isEmpty { bridgeOutputTracker.markOutput() }
      onTextDelta(delta)
    }
    let trackedToolActivity: ToolActivityHandler = { name, status, toolUseId, input in
      bridgeOutputTracker.markOutput()
      onToolActivity(name, status, toolUseId, input)
    }
    let trackedThinkingDelta: ThinkingDeltaHandler = { delta in
      if !delta.isEmpty { bridgeOutputTracker.markOutput() }
      onThinkingDelta(delta)
    }
    let trackedToolResultDisplay: ToolResultDisplayHandler = { callId, name, output in
      bridgeOutputTracker.markOutput()
      onToolResultDisplay(callId, name, output)
    }

    do {
      return try await runtime.query(
        clientId: clientId,
        requestId: requestId,
        sessionId: session.sessionId,
        prompt: prompt,
        surface: surface,
        mode: mode,
        imageData: imageData,
        attachments: attachments,
        expectedContext: expectedContext,
        onTextDelta: trackedTextDelta,
        onToolActivity: trackedToolActivity,
        onThinkingDelta: trackedThinkingDelta,
        onToolResultDisplay: trackedToolResultDisplay,
        onAuthRequired: onAuthRequired,
        onAuthSuccess: onAuthSuccess
      )
    } catch let error as BridgeError where usesManagedCloud && !bridgeOutputTracker.hasOutput && error.isSessionAuthenticationFailure {
      log("AgentBridge: session token rejected before output; refreshing token and retrying once")
      let refreshed: Bool
      do {
        refreshed = try await refreshAuthToken()
      } catch is CancellationError {
        throw CancellationError()
      } catch {
        throw BridgeError.authMissing
      }
      guard refreshed else {
        throw BridgeError.authMissing
      }
      let retryRequestId = UUID().uuidString
      activeRequestId = retryRequestId
      return try await runtime.query(
        clientId: clientId,
        requestId: retryRequestId,
        sessionId: session.sessionId,
        prompt: prompt,
        surface: surface,
        mode: mode,
        imageData: imageData,
        attachments: attachments,
        expectedContext: expectedContext,
        onTextDelta: onTextDelta,
        onToolActivity: onToolActivity,
        onThinkingDelta: onThinkingDelta,
        onToolResultDisplay: onToolResultDisplay,
        onAuthRequired: onAuthRequired,
        onAuthSuccess: onAuthSuccess
      )
    }
  }

  func interrupt() {
    guard let requestId = activeRequestId else { return }
    Task {
      await runtime.interrupt(clientId: clientId, requestId: requestId)
    }
  }

  @discardableResult
  func refreshAuthToken() async throws -> Bool {
    let authService = await MainActor.run { AuthService.shared }
    let token: String
    do {
      token = try await authService.getIdToken(forceRefresh: true)
    } catch {
      log("AgentBridge: refreshAuthToken failed: \(error.localizedDescription)")
      throw error
    }
    guard !token.isEmpty else {
      log("AgentBridge: refreshAuthToken got empty token; skipping push")
      return false
    }
    await runtime.refreshAuthToken(token)
    return true
  }

  private func ensureTokenRefreshTask() {
    guard tokenRefreshTask == nil else { return }
    tokenRefreshTask = Task { [weak self] in
      while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: 45 * 60 * 1_000_000_000)
        guard !Task.isCancelled else { break }
        _ = try? await self?.refreshAuthToken()
      }
    }
  }

  func testPlaywrightConnection() async throws -> Bool {
    let result = try await query(
      prompt:
        "Call browser_snapshot to verify the extension is connected. Only call that one tool, then report success or failure.",
      surface: .service("playwright_connection_test"),
      mode: "ask",
      onTextDelta: { _ in },
      onToolActivity: { name, status, _, _ in
        log("AgentBridge: test tool activity: \(name) \(status)")
      },
      onThinkingDelta: { _ in },
      onToolResultDisplay: { _, name, output in
        log("AgentBridge: test tool result: \(name) -> \(output.prefix(200))")
      }
    )
    let connected = result.text.contains("CONNECTED")
    log("AgentBridge: Playwright test response: \(result.text.prefix(300)), connected=\(connected)")
    return connected
  }

  private func cacheQuota(_ quota: APIClient.ChatUsageQuota) {
    lastKnownQuota = quota
  }

  private func migrateLegacyMainChatSessionsIfNeeded() async {
    let ownerId = await MainActor.run {
      RuntimeOwnerIdentity.currentOwnerId()
    }
    guard let ownerId, !ownerId.isEmpty else { return }
    let runtime = self.runtime
    let clientId = self.clientId
    let outcome = await LegacyMainChatSessionAliasMigration.migrate(
      ownerId: ownerId,
      defaults: .standard
    ) { entries in
      try await runtime.importLegacyMainChatSessions(clientId: clientId, entries: entries)
    }
    switch outcome {
    case .noAliases:
      break
    case .acknowledged(let removedCount):
      log(
        "Legacy main-chat alias migration acknowledged "
          + "(removed=\(removedCount) compat-owner=\(LegacyMainChatSessionAliasMigration.owner))")
    case .retained(let reason):
      log(
        "Legacy main-chat alias migration retained for restart retry "
          + "(reason=\(reason) compat-owner=\(LegacyMainChatSessionAliasMigration.owner))")
    }
  }
}

#if DEBUG
extension AgentBridge.QueryResult {
  /// Protocol-layer constructor for deterministic automation fixtures. Keeping
  /// the wire session placeholder here prevents UI/domain code from depending
  /// on transport identity fields.
  static func debugFixture(
    text: String,
    runId: String,
    attemptId: String,
    artifacts: [AgentArtifactProjection]
  ) -> Self {
    Self(
      text: text,
      costUsd: 0,
      omiSessionId: "debug-fixture-session",
      runId: runId,
      attemptId: attemptId,
      adapterSessionId: nil,
      terminalStatus: "succeeded",
      inputTokens: 0,
      outputTokens: 0,
      cacheReadTokens: 0,
      cacheWriteTokens: 0,
      artifacts: artifacts,
      completionDeltaArtifacts: artifacts
    )
  }
}
#endif

enum BridgeError: LocalizedError {
  case nodeNotFound
  case bridgeScriptNotFound
  case notRunning
  case encodingError
  case timeout
  case processExited
  case outOfMemory
  case stopped
  case restarting
  case requestAlreadyActive
  case agentError(String)
  case agentRuntimeFailure(AgentRuntimeFailure)
  case quotaExceeded(plan: String, unit: String, used: Double, limit: Double?, resetAtUnix: Int?)
  case authMissing

  var isSessionAuthenticationFailure: Bool {
    switch self {
    case .authMissing:
      return true
    case .agentError(let message):
      return Self.isSessionAuthenticationFailureMessage(message)
    case .agentRuntimeFailure(let failure):
      return Self.isSessionAuthenticationFailureMessage(failure.displayMessage)
        || (failure.technicalMessage.map(Self.isSessionAuthenticationFailureMessage) ?? false)
    case .nodeNotFound, .bridgeScriptNotFound, .notRunning, .encodingError, .timeout,
         .processExited, .outOfMemory, .stopped, .restarting, .requestAlreadyActive,
         .quotaExceeded:
      return false
    }
  }

  private static func isSessionAuthenticationFailureMessage(_ message: String) -> Bool {
    let normalized = message.lowercased()
    if normalized.contains("invalid_token") || normalized.contains("please sign in") {
      return true
    }

    let looksLikeAuthFailure =
      normalized.contains("401")
        || normalized.contains("unauthorized")
        || normalized.contains("authentication")

    guard looksLikeAuthFailure else {
      return false
    }

    return normalized.contains("token")
      || normalized.contains("session")
      || normalized.contains("sign in")
      || normalized.contains("signed in")
      || normalized.contains("firebase")
  }

  var errorDescription: String? {
    switch self {
    case .nodeNotFound:
      return AnalyticsManager.isDevBuild
        ? "Node.js not found. Run ./run.sh to set up AI components."
        : "Node.js not found. Please reinstall the app."
    case .bridgeScriptNotFound:
      return AnalyticsManager.isDevBuild
        ? "AI components missing. Run ./run.sh to install the agent runtime."
        : "AI components missing. Please reinstall the app."
    case .notRunning:
      return "AI is not running. Try sending your message again."
    case .encodingError:
      return "Failed to encode message"
    case .timeout:
      return "AI took too long to respond. Try again."
    case .processExited:
      return "AI stopped unexpectedly. Try sending your message again."
    case .outOfMemory:
      return "Not enough memory for AI chat. Close some apps and try again."
    case .stopped:
      return "Response stopped."
    case .restarting:
      return "AI is restarting. Try sending your message again."
    case .requestAlreadyActive:
      return "A response is already running for this chat."
    case .authMissing:
      return "Please sign in to use AI chat."
    case .agentRuntimeFailure(let failure):
      return failure.displayMessage
    case .agentError(let msg):
      return Self.userFacingAgentErrorMessage(msg)
    case .quotaExceeded(let plan, let unit, let used, let limit, _):
      let limitStr: String = {
        guard let limit = limit else { return "your monthly limit" }
        return unit == "cost_usd"
          ? String(format: "$%.0f of monthly chat usage", limit)
          : "\(Int(limit)) chat questions per month"
      }()
      let usedStr: String = {
        unit == "cost_usd"
          ? String(format: "$%.2f used", used)
          : "\(Int(used)) used"
      }()
      return "You've hit your \(plan) plan limit (\(limitStr); \(usedStr)). Upgrade in Settings → Plan and Usage, or wait until the next reset."
    }
  }

  private static func userFacingAgentErrorMessage(_ msg: String) -> String {
    guard !msg.isEmpty else { return "Something went wrong. Please try again." }
    let lower = msg.lowercased()
    if lower.contains("leaked") || lower.contains("api key") || lower.contains("api_key")
      || lower.contains("unauthorized") || lower.contains("permission denied")
      || lower.contains("invalid key") || lower.contains("forbidden")
    {
      return "AI service authentication error. Please update the app to the latest version."
    }
    if lower.contains("quota") || lower.contains("rate limit") || lower.contains("resource exhausted") {
      return "AI service is busy. Please try again in a moment."
    }
    if lower.contains("overloaded") || lower.contains("service unavailable") || lower.contains("internal error") {
      return "AI service is temporarily unavailable. Please try again later."
    }
    return msg
  }
}
