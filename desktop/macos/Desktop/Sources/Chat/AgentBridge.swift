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

private struct LegacyAliasDefaultsReference: @unchecked Sendable {
  let value: UserDefaults
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
    isAuthorizationCurrent: @escaping @Sendable () -> Bool = { true },
    importer:
      @Sendable ([LegacyMainChatSessionAliasEntry]) async throws ->
      LegacyMainChatSessionImportReceipt
  ) async -> Outcome {
    let ownerId = ownerId.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !ownerId.isEmpty else { return .retained(reason: "invalid_owner") }
    guard isAuthorizationCurrent() else {
      return .retained(reason: "owner_authorization_revoked")
    }
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
      pending.append(
        PendingAlias(
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

    let authorization = LocalMutationAuthorization(isAuthorizationCurrent)
    let defaultsReference = LegacyAliasDefaultsReference(value: defaults)
    let pendingAliases = pending
    do {
      let removedCount = try await authorization.withCommitLease {
        try authorization.require()
        var latest = defaultsReference.value.dictionary(forKey: defaultsKey) ?? [:]
        var removedCount = 0
        for alias in pendingAliases
        where latest[alias.defaultsKey] as? String == alias.storedSessionId {
          latest.removeValue(forKey: alias.defaultsKey)
          removedCount += 1
        }
        if latest.isEmpty {
          defaultsReference.value.removeObject(forKey: defaultsKey)
        } else {
          defaultsReference.value.set(latest, forKey: defaultsKey)
        }
        return removedCount
      }
      return .acknowledged(removedCount: removedCount)
    } catch LocalMutationAuthorizationError.revoked {
      return .retained(reason: "owner_authorization_revoked")
    } catch {
      return .retained(reason: "defaults_commit_failed")
    }
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
  let contextPlan: AgentConversationContextPlan

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
      let contextPlanDictionary = dictionary["contextPlan"] as? [String: Any],
      let contextPlan = AgentConversationContextPlan(dictionary: contextPlanDictionary),
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
    self.contextPlan = contextPlan
  }

  var freshness: AgentContextFreshness {
    AgentContextFreshness(
      version: version,
      generation: snapshotGeneration,
      rendererFingerprint: rendererFingerprint,
      capabilityVersion: capabilityVersion)
  }

  func sourceRevision(for source: AgentContextSource) -> String? {
    sourceOutcomes.first(where: { $0["source"] as? String == source.rawValue })?["sourceRevision"] as? String
  }

  var typedRecentTurns: [AgentContextRecentTurn] {
    recentTurns.compactMap(AgentContextRecentTurn.init(dictionary:))
  }
}

struct AgentConversationContextPlan: Equatable, Sendable {
  let version: Int
  let planId: String
  let semanticGuidanceVersion: String
  let semanticGuidance: String
  let retainedTurnStartSeq: Int?
  let retainedTurnEndSeq: Int?
  let retainedTurnCount: Int
  let totalTurnCount: Int
  let omittedTurnCount: Int
  let olderHistoryStrategy: String
  let stableCacheIdentity: String
  let dynamicContextIdentity: String

  init?(dictionary: [String: Any]) {
    guard
      let version = dictionary["version"] as? Int,
      version == 1,
      let planId = dictionary["planId"] as? String,
      let semanticGuidanceVersion = dictionary["semanticGuidanceVersion"] as? String,
      let semanticGuidance = dictionary["semanticGuidance"] as? String,
      let retainedTurnCount = dictionary["retainedTurnCount"] as? Int,
      let totalTurnCount = dictionary["totalTurnCount"] as? Int,
      let omittedTurnCount = dictionary["omittedTurnCount"] as? Int,
      let olderHistoryStrategy = dictionary["olderHistoryStrategy"] as? String,
      ["none", "truncated"].contains(olderHistoryStrategy),
      let stableCacheIdentity = dictionary["stableCacheIdentity"] as? String,
      let dynamicContextIdentity = dictionary["dynamicContextIdentity"] as? String,
      retainedTurnCount >= 0, totalTurnCount >= retainedTurnCount,
      omittedTurnCount == totalTurnCount - retainedTurnCount,
      olderHistoryStrategy == (omittedTurnCount > 0 ? "truncated" : "none")
    else { return nil }
    let retainedTurnStartSeq = dictionary["retainedTurnStartSeq"] as? Int
    let retainedTurnEndSeq = dictionary["retainedTurnEndSeq"] as? Int
    guard
      retainedTurnCount == 0
        ? retainedTurnStartSeq == nil && retainedTurnEndSeq == nil
        : retainedTurnStartSeq != nil && retainedTurnEndSeq != nil
    else { return nil }
    self.version = version
    self.planId = planId
    self.semanticGuidanceVersion = semanticGuidanceVersion
    self.semanticGuidance = semanticGuidance
    self.retainedTurnStartSeq = retainedTurnStartSeq
    self.retainedTurnEndSeq = retainedTurnEndSeq
    self.retainedTurnCount = retainedTurnCount
    self.totalTurnCount = totalTurnCount
    self.omittedTurnCount = omittedTurnCount
    self.olderHistoryStrategy = olderHistoryStrategy
    self.stableCacheIdentity = stableCacheIdentity
    self.dynamicContextIdentity = dynamicContextIdentity
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
  let rendererFingerprint: String
  let capabilityVersion: String
}

enum AgentQueryTerminalStatus: Equatable, Sendable {
  case succeeded
  case failed
  case timedOut
  case orphaned
  case cancelled
  case invalid(String?)

  init(wireValue: String?) {
    switch wireValue {
    case "succeeded": self = .succeeded
    case "failed": self = .failed
    case "timed_out": self = .timedOut
    case "orphaned": self = .orphaned
    case "cancelled": self = .cancelled
    default: self = .invalid(wireValue)
    }
  }

  var wireValue: String? {
    switch self {
    case .succeeded: return "succeeded"
    case .failed: return "failed"
    case .timedOut: return "timed_out"
    case .orphaned: return "orphaned"
    case .cancelled: return "cancelled"
    case .invalid(let value): return value
    }
  }
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
    let terminalStatus: AgentQueryTerminalStatus
    let failure: AgentRuntimeFailure?
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
      terminalStatus: String?,
      failure: AgentRuntimeFailure? = nil,
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
      self.terminalStatus = AgentQueryTerminalStatus(wireValue: terminalStatus)
      self.failure = failure
      self.inputTokens = inputTokens
      self.outputTokens = outputTokens
      self.cacheReadTokens = cacheReadTokens
      self.cacheWriteTokens = cacheWriteTokens
      self.artifacts = artifacts
      self.completionDeltaArtifacts = completionDeltaArtifacts
    }

    @discardableResult
    func requireSucceeded() throws -> QueryResult {
      switch terminalStatus {
      case .succeeded:
        return self
      case .cancelled:
        throw BridgeError.stopped
      case .failed, .timedOut, .orphaned:
        let raw = failure?.displayMessage ?? (text.isEmpty ? "Agent failed" : text)
        throw failure.map(BridgeError.agentRuntimeFailure) ?? BridgeError.agentError(raw)
      case .invalid:
        throw BridgeError.agentError("Agent returned an invalid terminal status")
      }
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

  private struct OwnerBoundQuota {
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    let quota: APIClient.ChatUsageQuota
  }

  private enum LifecycleOperationKind {
    case start
    case restart
  }

  private struct LifecycleFlight {
    let id: UUID
    let kind: LifecycleOperationKind
    let generation: UInt64
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
    let requiresCredentials: Bool
    var waiters: [CheckedContinuation<Void, Error>] = []
  }

  let harnessMode: String

  let clientId = UUID().uuidString
  let runtime: AgentRuntimeProcess
  private var registered = false
  private var synchronizedRuntimeAuthorityEpoch: UInt64?
  private var synchronizedRuntimeAuthorityOwnerID: String?
  private var activeRequestId: String?
  private var lastKnownQuota: OwnerBoundQuota?
  private var tokenRefreshTask: Task<Void, Never>?
  private var tokenRefreshTaskID: UUID?
  private var tokenRefreshAuthorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  private var stopTask: Task<Void, Never>?
  private var lifecycleGeneration: UInt64 = 0
  private var lifecycleFlight: LifecycleFlight?
  private var globalAuthRequiredHandler: AuthRequiredHandler?
  private var globalAuthSuccessHandler: AuthSuccessHandler?

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

  private func captureAuthorization(
    expectedOwnerID: String? = nil
  ) throws -> RuntimeOwnerAuthorizationSnapshot {
    guard
      let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot(
        expectedOwnerID: expectedOwnerID)
    else {
      throw BridgeError.authMissing
    }
    return snapshot
  }

  func resolveAuthorization(
    _ supplied: RuntimeOwnerAuthorizationSnapshot?,
    expectedOwnerID: String? = nil
  ) throws -> RuntimeOwnerAuthorizationSnapshot {
    guard let supplied else { return try captureAuthorization(expectedOwnerID: expectedOwnerID) }
    guard expectedOwnerID == nil || supplied.ownerID == expectedOwnerID,
      RuntimeOwnerIdentity.isAuthorizationCurrent(supplied)
    else {
      throw BridgeError.authMissing
    }
    return supplied
  }

  func setGlobalAuthHandlers(
    onAuthRequired: AuthRequiredHandler?,
    onAuthSuccess: AuthSuccessHandler?
  ) async {
    globalAuthRequiredHandler = onAuthRequired
    globalAuthSuccessHandler = onAuthSuccess
    guard registered else { return }
    guard let authorization = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      _ = await runtime.setGlobalAuthHandlers(
        clientId: clientId,
        authorizationSnapshot: nil,
        onAuthRequired: nil,
        onAuthSuccess: nil)
      return
    }
    let guardedAuthRequired: AuthRequiredHandler?
    if let onAuthRequired {
      guardedAuthRequired = { methods, authURL in
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
        onAuthRequired(methods, authURL)
      }
    } else {
      guardedAuthRequired = nil
    }
    let guardedAuthSuccess: AuthSuccessHandler?
    if let onAuthSuccess {
      guardedAuthSuccess = {
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
        onAuthSuccess()
      }
    } else {
      guardedAuthSuccess = nil
    }
    _ = await runtime.setGlobalAuthHandlers(
      clientId: clientId,
      authorizationSnapshot: authorization,
      onAuthRequired: guardedAuthRequired,
      onAuthSuccess: guardedAuthSuccess
    )
  }

  func start() async throws {
    let authorizationSnapshot = try captureAuthorization()
    try await start(authorizationSnapshot: authorizationSnapshot, requiresCredentials: true)
  }

  func start(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    requiresCredentials: Bool = true
  ) async throws {
    try await runLifecycleOperation(
      .start,
      authorizationSnapshot: authorizationSnapshot,
      requiresCredentials: requiresCredentials)
  }

  private func startJournalControl(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws {
    guard AppBuild.isNonProduction else {
      throw BridgeError.agentError("Journal control is disabled on production bundles")
    }
    try await start(authorizationSnapshot: authorizationSnapshot, requiresCredentials: false)
  }

  private func runLifecycleOperation(
    _ requestedKind: LifecycleOperationKind,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    requiresCredentials: Bool = true
  ) async throws {
    while let flight = lifecycleFlight {
      guard flight.authorizationSnapshot == authorizationSnapshot else {
        throw BridgeError.authMissing
      }
      try await waitForLifecycleFlight(id: flight.id)
      guard lifecycleGeneration == flight.generation, stopTask == nil,
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
      else {
        throw BridgeError.stopped
      }
      if requestedKind == .start, !requiresCredentials || flight.requiresCredentials {
        return
      }
      if flight.kind == .restart { return }
    }

    guard stopTask == nil else { throw BridgeError.restarting }
    let flightID = UUID()
    let generation = lifecycleGeneration
    lifecycleFlight = LifecycleFlight(
      id: flightID,
      kind: requestedKind,
      generation: generation,
      authorizationSnapshot: authorizationSnapshot,
      requiresCredentials: requiresCredentials)
    do {
      switch requestedKind {
      case .start:
        try await performStart(
          authorizationSnapshot: authorizationSnapshot,
          flightID: flightID,
          generation: generation,
          requiresCredentials: requiresCredentials)
      case .restart:
        try await performRestart(
          authorizationSnapshot: authorizationSnapshot,
          flightID: flightID,
          generation: generation)
      }
      finishLifecycleFlight(id: flightID, error: nil)
    } catch {
      finishLifecycleFlight(id: flightID, error: error)
      throw error
    }
  }

  private func performStart(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    flightID: UUID,
    generation: UInt64,
    requiresCredentials: Bool
  ) async throws {
    let ownerID = authorizationSnapshot.ownerID
    let processWasAlive = await runtime.isAlive
    try assertLifecycleFlightCurrent(
      id: flightID,
      generation: generation,
      authorizationSnapshot: authorizationSnapshot)
    let registeredThisCall = !registered || !processWasAlive
    let requiresManagedCredentials =
      isPiMonoHarness
      && AgentRuntimeCredentialPolicy.requiresManagedCredentials(
        requestedCredentials: requiresCredentials,
        isNonProduction: AppBuild.isNonProduction,
        hermeticFaultModelToken: AgentRuntimeCredentialPolicy.hermeticFaultModelToken(
          isNonProduction: AppBuild.isNonProduction,
          bundleIdentifier: AppBuild.bundleIdentifier))
    var acquiredRegistration = false
    do {
      if registeredThisCall {
        try await runtime.registerClient(
          clientId: clientId,
          harnessMode: harnessMode,
          authorizationSnapshot: authorizationSnapshot,
          requiresCredentials: requiresCredentials)
        acquiredRegistration = true
        try assertLifecycleFlightCurrent(
          id: flightID,
          generation: generation,
          authorizationSnapshot: authorizationSnapshot)
      }
      try await applyGlobalAuthHandlers(authorizationSnapshot: authorizationSnapshot)
      try assertLifecycleFlightCurrent(
        id: flightID,
        generation: generation,
        authorizationSnapshot: authorizationSnapshot)
      let status = await runtime.runtimeOwnerAuthorityStatus()
      try assertLifecycleFlightCurrent(
        id: flightID,
        generation: generation,
        authorizationSnapshot: authorizationSnapshot)
      let authorityNeedsSynchronization =
        !status.isSynchronized(
          ownerID: ownerID,
          requiresCredentials: requiresManagedCredentials)
        || synchronizedRuntimeAuthorityEpoch != status.epoch
        || synchronizedRuntimeAuthorityOwnerID != ownerID
      if authorityNeedsSynchronization {
        await synchronizeRuntimeAuthority(
          authorizationSnapshot: authorizationSnapshot,
          requiresCredentials: requiresManagedCredentials)
        try assertLifecycleFlightCurrent(
          id: flightID,
          generation: generation,
          authorizationSnapshot: authorizationSnapshot)
        let synchronized = await runtime.runtimeOwnerAuthorityStatus()
        try assertLifecycleFlightCurrent(
          id: flightID,
          generation: generation,
          authorizationSnapshot: authorizationSnapshot)
        guard
          synchronized.isSynchronized(
            ownerID: ownerID,
            requiresCredentials: requiresManagedCredentials)
        else {
          throw BridgeError.authMissing
        }
        synchronizedRuntimeAuthorityEpoch = synchronized.epoch
        synchronizedRuntimeAuthorityOwnerID = ownerID
      }
      if registeredThisCall || authorityNeedsSynchronization {
        await migrateLegacyMainChatSessionsIfNeeded(
          authorizationSnapshot: authorizationSnapshot)
        try assertLifecycleFlightCurrent(
          id: flightID,
          generation: generation,
          authorizationSnapshot: authorizationSnapshot)
      }
      registered = true
    } catch {
      if acquiredRegistration {
        await runtime.unregisterClient(clientId: clientId)
      }
      throw error
    }
  }

  func restart() async throws {
    guard let authorizationSnapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      throw BridgeError.authMissing
    }
    try await runLifecycleOperation(
      .restart,
      authorizationSnapshot: authorizationSnapshot)
  }

  private func performRestart(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    flightID: UUID,
    generation: UInt64
  ) async throws {
    let processIsAlive = await runtime.isAlive
    try assertLifecycleFlightCurrent(
      id: flightID,
      generation: generation,
      authorizationSnapshot: authorizationSnapshot)
    guard registered, processIsAlive else {
      try await performStart(
        authorizationSnapshot: authorizationSnapshot,
        flightID: flightID,
        generation: generation,
        requiresCredentials: true)
      return
    }
    try await runtime.restart(
      clientId: clientId,
      harnessMode: harnessMode,
      authorizationSnapshot: authorizationSnapshot)
    try assertLifecycleFlightCurrent(
      id: flightID,
      generation: generation,
      authorizationSnapshot: authorizationSnapshot)
    synchronizedRuntimeAuthorityEpoch = nil
    synchronizedRuntimeAuthorityOwnerID = nil
    try await applyGlobalAuthHandlers(authorizationSnapshot: authorizationSnapshot)
    try assertLifecycleFlightCurrent(
      id: flightID,
      generation: generation,
      authorizationSnapshot: authorizationSnapshot)
    await synchronizeRuntimeAuthority(
      authorizationSnapshot: authorizationSnapshot,
      requiresCredentials: isPiMonoHarness)
    try assertLifecycleFlightCurrent(
      id: flightID,
      generation: generation,
      authorizationSnapshot: authorizationSnapshot)
    let ownerID = authorizationSnapshot.ownerID
    let status = await runtime.runtimeOwnerAuthorityStatus()
    try assertLifecycleFlightCurrent(
      id: flightID,
      generation: generation,
      authorizationSnapshot: authorizationSnapshot)
    guard
      status.isSynchronized(
        ownerID: ownerID,
        requiresCredentials: isPiMonoHarness)
    else {
      throw BridgeError.authMissing
    }
    synchronizedRuntimeAuthorityEpoch = status.epoch
    synchronizedRuntimeAuthorityOwnerID = ownerID
    await migrateLegacyMainChatSessionsIfNeeded(
      authorizationSnapshot: authorizationSnapshot)
    try assertLifecycleFlightCurrent(
      id: flightID,
      generation: generation,
      authorizationSnapshot: authorizationSnapshot)
    registered = true
  }

  private func assertLifecycleFlightCurrent(
    id: UUID,
    generation: UInt64,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) throws {
    try Task.checkCancellation()
    guard lifecycleFlight?.id == id, lifecycleGeneration == generation, stopTask == nil else {
      throw BridgeError.stopped
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw BridgeError.authMissing
    }
  }

  private func waitForLifecycleFlight(id: UUID) async throws {
    try await withCheckedThrowingContinuation {
      (continuation: CheckedContinuation<Void, Error>) in
      guard var flight = lifecycleFlight, flight.id == id else {
        continuation.resume(throwing: BridgeError.stopped)
        return
      }
      flight.waiters.append(continuation)
      lifecycleFlight = flight
    }
  }

  private func finishLifecycleFlight(id: UUID, error: Error?) {
    guard let flight = lifecycleFlight, flight.id == id else { return }
    lifecycleFlight = nil
    for waiter in flight.waiters {
      if let error {
        waiter.resume(throwing: error)
      } else {
        waiter.resume()
      }
    }
  }

  private func applyGlobalAuthHandlers(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      throw BridgeError.authMissing
    }
    let guardedAuthRequired: AuthRequiredHandler?
    if let globalAuthRequiredHandler {
      guardedAuthRequired = { methods, authURL in
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
        globalAuthRequiredHandler(methods, authURL)
      }
    } else {
      guardedAuthRequired = nil
    }
    let guardedAuthSuccess: AuthSuccessHandler?
    if let globalAuthSuccessHandler {
      guardedAuthSuccess = {
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
        globalAuthSuccessHandler()
      }
    } else {
      guardedAuthSuccess = nil
    }
    let applied = await runtime.setGlobalAuthHandlers(
      clientId: clientId,
      authorizationSnapshot: authorizationSnapshot,
      onAuthRequired: guardedAuthRequired,
      onAuthSuccess: guardedAuthSuccess)
    guard applied else { throw BridgeError.stopped }
  }

  /// Reset client registration after an unexpected process exit so `restart()`/`start()`
  /// can spawn a fresh Node bridge (the process is already gone).
  func prepareForCrashRecovery() {
    lifecycleGeneration &+= 1
    tokenRefreshTask?.cancel()
    tokenRefreshTask = nil
    tokenRefreshTaskID = nil
    tokenRefreshAuthorizationSnapshot = nil
    registered = false
    synchronizedRuntimeAuthorityEpoch = nil
    synchronizedRuntimeAuthorityOwnerID = nil
    activeRequestId = nil
    lastKnownQuota = nil
  }

  func stopAndWaitForExit() async {
    await stop()
  }

  func stop() async {
    if let stopTask {
      await stopTask.value
      return
    }
    tokenRefreshTask?.cancel()
    tokenRefreshTask = nil
    tokenRefreshTaskID = nil
    tokenRefreshAuthorizationSnapshot = nil
    lifecycleGeneration &+= 1
    let flightID = lifecycleFlight?.id
    registered = false
    synchronizedRuntimeAuthorityEpoch = nil
    synchronizedRuntimeAuthorityOwnerID = nil
    activeRequestId = nil
    lastKnownQuota = nil
    let runtime = self.runtime
    let clientId = self.clientId
    let task = Task { [weak self] in
      await runtime.unregisterClient(clientId: clientId)
      if let flightID {
        do {
          try await self?.waitForLifecycleFlight(id: flightID)
        } catch {
          // Stop invalidated this flight; only its completion matters here.
        }
      }
      // A second idempotent unregister closes the interval between the first
      // unregister and a suspended registration attempt observing revocation.
      await runtime.unregisterClient(clientId: clientId)
    }
    stopTask = task
    await task.value
    stopTask = nil
  }

  func configureDefaultExecutionProfile(
    adapterId: String,
    modelProfile: String?,
    workingDirectory: String,
    expectedPreferenceGeneration: Int? = nil
  ) async throws -> AgentDefaultExecutionProfile {
    let authorization = try captureAuthorization()
    try await start(authorizationSnapshot: authorization)
    if adapterId == AgentAdapterId.piMono.rawValue {
      ensureTokenRefreshTask(authorizationSnapshot: authorization)
      _ = try? await refreshAuthToken(authorizationSnapshot: authorization)
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw BridgeError.authMissing
    }
    return try await runtime.configureDefaultExecutionProfile(
      clientId: clientId,
      adapterId: adapterId,
      modelProfile: modelProfile,
      workingDirectory: workingDirectory,
      expectedPreferenceGeneration: expectedPreferenceGeneration,
      authorizationSnapshot: authorization
    )
  }

  func migrateSessionExecutionProfile(
    sessionId: String,
    expectedProfileGeneration: Int,
    adapterId: String,
    modelProfile: String?,
    workingDirectory: String
  ) async throws -> AgentSessionProfileMigration {
    let authorization = try captureAuthorization()
    try await start(authorizationSnapshot: authorization)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw BridgeError.authMissing
    }
    return try await runtime.migrateSessionExecutionProfile(
      clientId: clientId,
      sessionId: sessionId,
      expectedProfileGeneration: expectedProfileGeneration,
      adapterId: adapterId,
      modelProfile: modelProfile,
      workingDirectory: workingDirectory,
      authorizationSnapshot: authorization
    )
  }

  func warmupSession(
    _ session: AgentSurfaceSession,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async {
    guard let authorization = try? resolveAuthorization(authorizationSnapshot) else { return }
    do {
      try await start(authorizationSnapshot: authorization)
    } catch {
      return
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
    await runtime.warmupSession(
      clientId: clientId,
      sessionId: session.sessionId,
      profileGeneration: session.profile.profileGeneration,
      authorizationSnapshot: authorization
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
    payload: [String: Any],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentContextSourceUpdateReceipt {
    try await updateContextSource(
      sessionId: sessionId,
      surfaceKind: surfaceKind,
      source: source,
      sourceRevision: sourceRevision,
      outcome: outcome,
      capturedAtMs: capturedAtMs,
      expiresAtMs: expiresAtMs,
      payload: RuntimeJSONPayloadBox(payload),
      authorizationSnapshot: authorizationSnapshot
    )
  }

  /// Sendable-safe entry point for cross-actor callers. Boxes the JSON payload
  /// so it can cross actor boundaries without triggering data-race diagnostics.
  func updateContextSource(
    sessionId: String,
    surfaceKind: String,
    source: AgentContextSource,
    sourceRevision: String,
    outcome: AgentContextSourceOutcome,
    capturedAtMs: Int,
    expiresAtMs: Int? = nil,
    payload: RuntimeJSONPayloadBox,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentContextSourceUpdateReceipt {
    let authorization = try resolveAuthorization(authorizationSnapshot)
    try await start(authorizationSnapshot: authorization)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw BridgeError.authMissing
    }
    return try await runtime.updateContextSource(
      clientId: clientId,
      sessionId: sessionId,
      surfaceKind: surfaceKind,
      source: source,
      sourceRevision: sourceRevision,
      outcome: outcome,
      capturedAtMs: capturedAtMs,
      expiresAtMs: expiresAtMs,
      payload: payload,
      authorizationSnapshot: authorization
    )
  }

  func getContextSnapshot(
    sessionId: String,
    surfaceKind: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentContextSnapshot {
    let authorization = try resolveAuthorization(authorizationSnapshot)
    try await start(authorizationSnapshot: authorization)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw BridgeError.authMissing
    }
    return try await runtime.getContextSnapshot(
      clientId: clientId,
      sessionId: sessionId,
      surfaceKind: surfaceKind,
      authorizationSnapshot: authorization)
  }

  func invalidateSurface(_ surface: AgentSurfaceReference) async {
    guard let authorization = try? captureAuthorization() else { return }
    do {
      try await start(authorizationSnapshot: authorization)
    } catch {
      return
    }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
    await runtime.invalidateSurface(
      clientId: clientId,
      surface: surface,
      authorizationSnapshot: authorization)
  }

  func importLegacyMainChatSessions(
    _ entries: [LegacyMainChatSessionAliasEntry],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> LegacyMainChatSessionImportReceipt {
    let authorization = try resolveAuthorization(authorizationSnapshot)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.importLegacyMainChatSessions(
      clientId: clientId,
      entries: entries,
      authorizationSnapshot: authorization)
  }

  func recordJournalTurn(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    turn: KernelJournalTurnWrite,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> KernelJournalTurn {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.recordJournalTurn(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      turn: turn,
      authorizationSnapshot: authorization
    )
  }

  func recordJournalExchange(
    surface: AgentSurfaceReference,
    ownerID: String,
    turns: [KernelJournalTurnWrite],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentRuntimeProcess.JournalOperationResult {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.recordJournalExchange(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      turns: turns,
      authorizationSnapshot: authorization
    )
  }

  func updateJournalTurn(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    update: KernelJournalTurnUpdate,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> KernelJournalTurn {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.updateJournalTurn(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      update: update,
      authorizationSnapshot: authorization
    )
  }

  func terminalizeJournalTurn(
    surface: AgentSurfaceReference,
    ownerID: String,
    terminalization: KernelJournalTurnTerminalization,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> KernelJournalTurn {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.terminalizeJournalTurn(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      terminalization: terminalization,
      authorizationSnapshot: authorization
    )
  }

  func listJournalTurns(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    afterTurnSeq: Int = 0,
    limit: Int = 100,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentRuntimeProcess.JournalOperationResult {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.listJournalTurns(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      afterTurnSeq: afterTurnSeq,
      limit: limit,
      authorizationSnapshot: authorization
    )
  }

  func listJournalTurnsForControl(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    afterTurnSeq: Int = 0,
    limit: Int = 100,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> AgentRuntimeProcess.JournalOperationResult {
    guard AppBuild.isNonProduction else {
      throw BridgeError.agentError("Journal control is disabled on production bundles")
    }
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await startJournalControl(authorizationSnapshot: authorization)
    return try await runtime.listJournalTurns(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      afterTurnSeq: afterTurnSeq,
      limit: limit,
      authorizationSnapshot: authorization
    )
  }

  func importRemoteJournalTurn(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    turn: KernelJournalRemoteTurn,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> KernelJournalTurn {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.importRemoteJournalTurn(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      turn: turn,
      authorizationSnapshot: authorization
    )
  }

  func clearJournalTurns(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    expectedGeneration: Int? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> Int {
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.clearJournalTurns(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      expectedGeneration: expectedGeneration,
      authorizationSnapshot: authorization
    )
  }

  func clearJournalTurnsForControl(
    surface: AgentSurfaceReference,
    ownerID: String? = nil,
    expectedGeneration: Int? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> Int {
    guard AppBuild.isNonProduction else {
      throw BridgeError.agentError("Journal control is disabled on production bundles")
    }
    let authorization = try resolveAuthorization(
      authorizationSnapshot,
      expectedOwnerID: ownerID)
    try await startJournalControl(authorizationSnapshot: authorization)
    return try await runtime.clearJournalTurns(
      clientId: clientId,
      surface: surface,
      ownerID: ownerID,
      expectedGeneration: expectedGeneration,
      authorizationSnapshot: authorization
    )
  }

  func setJournalTurnChangedHandler(
    _ handler: @escaping AgentRuntimeProcess.JournalTurnChangedHandler
  ) async {
    await runtime.setJournalTurnChangedHandler(handler)
  }

  func controlTool(
    name: String,
    input: [String: Any],
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> String {
    let authorization = try resolveAuthorization(authorizationSnapshot)
    try await start(authorizationSnapshot: authorization)
    return try await runtime.directControlTool(
      clientId: clientId,
      harnessMode: harnessMode,
      name: name,
      input: RuntimeJSONPayloadBox(input),
      authorizationSnapshot: authorization
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
        input: RuntimeJSONPayloadBox(input),
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
    producingTurnId: String? = nil,
    expectedContext: AgentContextFreshness? = nil,
    reasoningEffort: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    onTextDelta: @escaping TextDeltaHandler,
    onToolActivity: @escaping ToolActivityHandler,
    onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
    onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
    onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
    onAuthSuccess: @escaping AuthSuccessHandler = {}
  ) async throws -> QueryResult {
    let authorization = try resolveAuthorization(authorizationSnapshot)
    try await start(authorizationSnapshot: authorization)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw BridgeError.authMissing
    }
    let session = try await runtime.resolveSurfaceSession(
      clientId: clientId,
      surface: surface,
      title: nil,
      creationProfile: nil,
      authorizationSnapshot: authorization)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw BridgeError.authMissing
    }
    return try await query(
      prompt: prompt,
      session: session,
      surface: surface,
      mode: mode,
      imageData: imageData,
      attachments: attachments,
      producingTurnId: producingTurnId,
      expectedContext: expectedContext,
      reasoningEffort: reasoningEffort,
      authorizationSnapshot: authorization,
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
    producingTurnId: String? = nil,
    expectedContext: AgentContextFreshness? = nil,
    reasoningEffort: String? = nil,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil,
    onTextDelta: @escaping TextDeltaHandler,
    onToolActivity: @escaping ToolActivityHandler,
    onThinkingDelta: @escaping ThinkingDeltaHandler = { _ in },
    onToolResultDisplay: @escaping ToolResultDisplayHandler = { _, _, _ in },
    onAuthRequired: @escaping AuthRequiredHandler = { _, _ in },
    onAuthSuccess: @escaping AuthSuccessHandler = {}
  ) async throws -> QueryResult {
    let authorization = try authorizationSnapshot ?? captureAuthorization()
    try await start(authorizationSnapshot: authorization)
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw BridgeError.authMissing
    }
    let guardedAuthRequired: AuthRequiredHandler = { methods, authURL in
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
      onAuthRequired(methods, authURL)
    }
    let guardedAuthSuccess: AuthSuccessHandler = {
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
      onAuthSuccess()
    }
    let handlersApplied = await runtime.setGlobalAuthHandlers(
      clientId: clientId,
      authorizationSnapshot: authorization,
      onAuthRequired: guardedAuthRequired,
      onAuthSuccess: guardedAuthSuccess)
    guard handlersApplied else { throw BridgeError.stopped }
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
      throw BridgeError.authMissing
    }

    guard activeRequestId == nil else {
      throw BridgeError.requestAlreadyActive
    }

    let usesManagedCloud = session.profile.credentialScope == .managedCloud
    if usesManagedCloud {
      if let cached = currentQuota(for: authorization), !cached.allowed {
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
      Task { [weak self, authorization] in
        if let quota = await APIClient.shared.fetchChatUsageQuota(
          authorizationSnapshot: authorization)
        {
          guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
          await self?.cacheQuota(quota, authorizationSnapshot: authorization)
        }
      }
    }

    let requestId = UUID().uuidString
    activeRequestId = requestId
    defer { activeRequestId = nil }

    let bridgeOutputTracker = BridgeOutputTracker()
    let trackedTextDelta: TextDeltaHandler = { delta in
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
      if !delta.isEmpty { bridgeOutputTracker.markOutput() }
      onTextDelta(delta)
    }
    let trackedToolActivity: ToolActivityHandler = { name, status, toolUseId, input in
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
      bridgeOutputTracker.markOutput()
      onToolActivity(name, status, toolUseId, input)
    }
    let trackedThinkingDelta: ThinkingDeltaHandler = { delta in
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
      if !delta.isEmpty { bridgeOutputTracker.markOutput() }
      onThinkingDelta(delta)
    }
    let trackedToolResultDisplay: ToolResultDisplayHandler = { callId, name, output in
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return }
      bridgeOutputTracker.markOutput()
      onToolResultDisplay(callId, name, output)
    }

    do {
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
        throw BridgeError.authMissing
      }
      return try await runtime.query(
        clientId: clientId,
        requestId: requestId,
        sessionId: session.sessionId,
        prompt: prompt,
        surface: surface,
        mode: mode,
        imageData: imageData,
        attachments: attachments,
        producingTurnId: producingTurnId,
        expectedContext: expectedContext,
        reasoningEffort: reasoningEffort,
        authorizationSnapshot: authorization,
        onTextDelta: trackedTextDelta,
        onToolActivity: trackedToolActivity,
        onThinkingDelta: trackedThinkingDelta,
        onToolResultDisplay: trackedToolResultDisplay,
        onAuthRequired: guardedAuthRequired,
        onAuthSuccess: guardedAuthSuccess
      )
    } catch let error as BridgeError
      where usesManagedCloud && !bridgeOutputTracker.hasOutput && error.isSessionAuthenticationFailure
    {
      log("AgentBridge: session token rejected before output; refreshing token and retrying once")
      let refreshed: Bool
      do {
        refreshed = try await refreshAuthToken(authorizationSnapshot: authorization)
      } catch is CancellationError {
        throw CancellationError()
      } catch {
        throw BridgeError.authMissing
      }
      guard refreshed else {
        throw BridgeError.authMissing
      }
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else {
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
        producingTurnId: producingTurnId,
        expectedContext: expectedContext,
        reasoningEffort: reasoningEffort,
        authorizationSnapshot: authorization,
        onTextDelta: trackedTextDelta,
        onToolActivity: trackedToolActivity,
        onThinkingDelta: trackedThinkingDelta,
        onToolResultDisplay: trackedToolResultDisplay,
        onAuthRequired: guardedAuthRequired,
        onAuthSuccess: guardedAuthSuccess
      )
    }
  }

  func interrupt(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async {
    guard let requestId = activeRequestId else { return }
    guard let authorization = try? resolveAuthorization(authorizationSnapshot) else { return }
    await runtime.interrupt(
      clientId: clientId,
      requestId: requestId,
      authorizationSnapshot: authorization)
  }

  @discardableResult
  func refreshAuthToken(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot? = nil
  ) async throws -> Bool {
    do {
      let runtime = self.runtime
      let refreshed = try await Self.refreshOwnerBoundToken(
        captureAuthorization: {
          authorizationSnapshot ?? RuntimeOwnerIdentity.captureAuthorizationSnapshot()
        },
        authorizationOwnerId: { snapshot in
          snapshot.ownerID
        },
        isAuthorizationCurrent: { snapshot in
          RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot)
        },
        fetchAuthHeader: { expectedOwnerId in
          try await AuthService.shared.getAuthHeader(
            forceRefresh: true,
            expectedUserId: expectedOwnerId
          )
        },
        sendToken: { token, expectedOwnerId, snapshot in
          await runtime.refreshAuthToken(
            token,
            expectedOwnerId: expectedOwnerId,
            authorizationSnapshot: snapshot)
        }
      )
      if !refreshed {
        log("AgentBridge: refreshAuthToken owner changed or token was unavailable; skipping push")
      }
      return refreshed
    } catch {
      log("AgentBridge: refreshAuthToken failed: \(error.localizedDescription)")
      throw error
    }
  }

  /// Fetches and sends one token under a single immutable owner identity.
  /// The second owner read closes the suspension window around the credential
  /// fetch; the runtime performs the same comparison again at the send boundary.
  nonisolated static func refreshOwnerBoundToken<Authorization: Sendable>(
    captureAuthorization: @escaping @Sendable () async -> Authorization?,
    authorizationOwnerId: @escaping @Sendable (_ authorization: Authorization) -> String,
    isAuthorizationCurrent:
      @escaping @Sendable (
        _ authorization: Authorization
      ) async -> Bool,
    fetchAuthHeader: @escaping @Sendable (_ expectedOwnerId: String) async throws -> String,
    sendToken:
      @escaping @Sendable (
        _ token: String, _ expectedOwnerId: String, _ authorization: Authorization
      ) async -> Bool
  ) async throws -> Bool {
    guard let authorization = await captureAuthorization() else {
      return false
    }
    let expectedOwnerId = authorizationOwnerId(authorization)
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !expectedOwnerId.isEmpty else { return false }
    guard await isAuthorizationCurrent(authorization) else { return false }
    let header = try await fetchAuthHeader(expectedOwnerId)
    guard
      let token = bearerToken(from: header),
      await isAuthorizationCurrent(authorization)
    else {
      return false
    }
    return await sendToken(token, expectedOwnerId, authorization)
  }

  private nonisolated static func bearerToken(from header: String) -> String? {
    let prefix = "Bearer "
    guard header.hasPrefix(prefix) else { return nil }
    let token = String(header.dropFirst(prefix.count))
      .trimmingCharacters(in: .whitespacesAndNewlines)
    return token.isEmpty ? nil : token
  }

  private func ensureTokenRefreshTask(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    if tokenRefreshTask != nil,
      tokenRefreshAuthorizationSnapshot == authorizationSnapshot
    {
      return
    }
    tokenRefreshTask?.cancel()
    let taskID = UUID()
    tokenRefreshTaskID = taskID
    tokenRefreshAuthorizationSnapshot = authorizationSnapshot
    tokenRefreshTask = Task { [weak self] in
      defer {
        Task { [weak self] in
          await self?.finishTokenRefreshTask(id: taskID)
        }
      }
      while !Task.isCancelled {
        try? await Task.sleep(nanoseconds: 45 * 60 * 1_000_000_000)
        guard !Task.isCancelled else { break }
        guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { break }
        let refreshed = try? await self?.refreshAuthToken(
          authorizationSnapshot: authorizationSnapshot)
        guard refreshed == true else { break }
      }
    }
  }

  private func finishTokenRefreshTask(id: UUID) {
    guard tokenRefreshTaskID == id else { return }
    tokenRefreshTask = nil
    tokenRefreshTaskID = nil
    tokenRefreshAuthorizationSnapshot = nil
  }

  /// Node starts with a non-authoritative local placeholder owner. Every
  /// harness must replace it before the first owner-scoped RPC; pi-mono also
  /// receives the credential it needs, while local adapters use an owner-only
  /// handshake and remain independent of managed-cloud token availability.
  nonisolated static func synchronizeAuthorityForStart(
    requiresCredentials: Bool,
    refreshCredentials: () async throws -> Bool,
    refreshOwner: () async -> Void
  ) async {
    guard requiresCredentials else {
      await refreshOwner()
      return
    }
    do {
      if try await refreshCredentials() == false {
        await refreshOwner()
      }
    } catch {
      await refreshOwner()
    }
  }

  private func synchronizeRuntimeAuthority(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    requiresCredentials: Bool
  ) async {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    if requiresCredentials {
      ensureTokenRefreshTask(authorizationSnapshot: authorizationSnapshot)
    }
    await Self.synchronizeAuthorityForStart(
      requiresCredentials: requiresCredentials,
      refreshCredentials: { [weak self] in
        guard let self else { return false }
        return try await self.refreshAuthToken(authorizationSnapshot: authorizationSnapshot)
      },
      refreshOwner: { [weak self] in
        guard let self else { return }
        await self.runtime.refreshRuntimeOwner(
          expectedOwnerId: authorizationSnapshot.ownerID,
          authorizationSnapshot: authorizationSnapshot)
      })
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
    let connected = try result.requireSucceeded().text.contains("CONNECTED")
    log("AgentBridge: Playwright test response: \(result.text.prefix(300)), connected=\(connected)")
    return connected
  }

  private func currentQuota(
    for authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) -> APIClient.ChatUsageQuota? {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else {
      lastKnownQuota = nil
      return nil
    }
    guard lastKnownQuota?.authorizationSnapshot == authorizationSnapshot else {
      lastKnownQuota = nil
      return nil
    }
    return lastKnownQuota?.quota
  }

  private func cacheQuota(
    _ quota: APIClient.ChatUsageQuota,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    lastKnownQuota = OwnerBoundQuota(
      authorizationSnapshot: authorizationSnapshot,
      quota: quota)
  }

  private func migrateLegacyMainChatSessionsIfNeeded(
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async {
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
    let ownerId = authorizationSnapshot.ownerID
    let runtime = self.runtime
    let clientId = self.clientId
    let outcome = await LegacyMainChatSessionAliasMigration.migrate(
      ownerId: ownerId,
      defaults: .standard,
      isAuthorizationCurrent: {
        RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot)
      },
      importer: { entries in
        try await runtime.importLegacyMainChatSessions(
          clientId: clientId,
          entries: entries,
          authorizationSnapshot: authorizationSnapshot)
      })
    guard RuntimeOwnerIdentity.isAuthorizationCurrent(authorizationSnapshot) else { return }
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
  case failedToStart(AgentRuntimeBridgeLifecycle.StartFailure)
  case stopped
  case restarting
  case requestAlreadyActive
  case agentError(String)
  case agentRuntimeFailure(AgentRuntimeFailure)
  case quotaExceeded(plan: String, unit: String, used: Double, limit: Double?, resetAtUnix: Int?)
  case authMissing

  var isContextSnapshotProjectionMismatch: Bool {
    let exactCode = "context_snapshot_projection_mismatch"
    switch self {
    case .agentError(let message):
      return message == exactCode
    case .agentRuntimeFailure(let failure):
      guard failure.source == "runtime" else { return false }
      return failure.userMessage == exactCode || failure.technicalMessage == exactCode
    case .nodeNotFound, .bridgeScriptNotFound, .notRunning, .encodingError, .timeout,
      .processExited, .outOfMemory, .failedToStart, .stopped, .restarting, .requestAlreadyActive,
      .quotaExceeded, .authMissing:
      return false
    }
  }

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
      .processExited, .outOfMemory, .failedToStart, .stopped, .restarting, .requestAlreadyActive,
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
    case .failedToStart:
      return "AI couldn't start. Please try again."
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
      return
        "You've hit your \(plan) plan limit (\(limitStr); \(usedStr)). Upgrade in Settings → Plan and Usage, or wait until the next reset."
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
