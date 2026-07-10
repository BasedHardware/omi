import CryptoKit
import Foundation

enum TaskContextEventKind: String, Codable, CaseIterable {
  case person
  case appWindow = "app_window"
  case document
  case meeting
  case freeTime = "free_time"
  case dependency
  case agent

  var recommendationSignal: OmiAPI.ContextMatchSignal? {
    switch self {
    case .person: .person
    case .appWindow: .app
    case .document: .document
    case .meeting: .meeting
    case .freeTime: .free_time
    case .dependency: .dependency
    case .agent: .agent
    }
  }
}

enum TaskContextUrgency: String, Codable {
  case canWait = "can_wait"
  case timeSensitive = "time_sensitive"
}

struct TaskContextSubject: Hashable {
  let kind: OmiAPI.RecommendationSubjectKind
  let id: String
  let workstreamID: String?

  static func == (lhs: Self, rhs: Self) -> Bool {
    lhs.kind.rawValue == rhs.kind.rawValue && lhs.id == rhs.id
  }

  func hash(into hasher: inout Hasher) {
    hasher.combine(kind.rawValue)
    hasher.combine(id)
  }
}

/// A privacy-bounded local event. Raw window titles, person names, document names,
/// and meeting text are normalized and hashed before this value exists.
struct TaskLocalContextEvent: Equatable {
  static let schemaVersion = 1

  let kind: TaskContextEventKind
  let referenceHash: String
  let subject: TaskContextSubject?
  let urgency: TaskContextUrgency
  let occurredAt: Date
  let expiresAt: Date

  var coalescingKey: String {
    subject?.workstreamID ?? subject?.id ?? "local-context"
  }

  static func normalized(
    kind: TaskContextEventKind,
    rawReference: String,
    subject: TaskContextSubject? = nil,
    urgency: TaskContextUrgency = .canWait,
    occurredAt: Date = Date(),
    lifetime: TimeInterval = 5 * 60
  ) -> TaskLocalContextEvent? {
    let normalized = rawReference
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .lowercased()
    guard !normalized.isEmpty, lifetime > 0 else { return nil }
    let digest = SHA256.hash(data: Data(normalized.utf8))
      .map { String(format: "%02x", $0) }.joined()
    return TaskLocalContextEvent(
      kind: kind,
      referenceHash: "sha256:\(digest)",
      subject: subject,
      urgency: urgency,
      occurredAt: occurredAt,
      expiresAt: occurredAt.addingTimeInterval(lifetime)
    )
  }

  static func appWindow(
    appName: String,
    windowTitle: String?,
    subject: TaskContextSubject? = nil,
    occurredAt: Date = Date()
  ) -> TaskLocalContextEvent? {
    let normalizedTitle = ContextDetection.normalizeWindowTitle(windowTitle) ?? "untitled"
    return normalized(
      kind: .appWindow,
      rawReference: "\(appName)\n\(normalizedTitle)",
      subject: subject,
      occurredAt: occurredAt
    )
  }

  func attaching(subject: TaskContextSubject) -> TaskLocalContextEvent {
    TaskLocalContextEvent(
      kind: kind,
      referenceHash: referenceHash,
      subject: subject,
      urgency: urgency,
      occurredAt: occurredAt,
      expiresAt: expiresAt
    )
  }
}

/// Learns only explicit, device-local context-to-subject associations. The
/// matcher persists hashes and canonical IDs, never raw app/window/person text.
/// A successful recommendation open binds the recent context so reopening that
/// Slack thread or document can resume the same workstream on the next visit.
@MainActor
final class TaskContextSubjectMatcher {
  static let shared = TaskContextSubjectMatcher()

  private struct Entry: Codable {
    let referenceHash: String
    let subjectKind: String
    let subjectID: String
    let workstreamID: String?
    let updatedAt: Date
  }

  private struct RecentContext {
    let referenceHash: String
    let occurredAt: Date
  }

  private let defaults: UserDefaults
  private let fixedOwnerID: String?
  private var activeOwnerHash: String
  private var entries: [String: Entry]
  private var currentContext: RecentContext?

  init(defaults: UserDefaults = .standard, ownerID: String? = nil) {
    self.defaults = defaults
    fixedOwnerID = ownerID
    activeOwnerHash = Self.ownerHash(ownerID ?? defaults.string(forKey: .authUserId) ?? "signed-out")
    if let data = defaults.data(forKey: .taskContextSubjectMatches(ownerHash: activeOwnerHash)),
      let decoded = try? JSONDecoder().decode([Entry].self, from: data)
    {
      entries = Dictionary(uniqueKeysWithValues: decoded.map { ($0.referenceHash, $0) })
    } else {
      entries = [:]
    }
    prune(now: Date())
  }

  func resolve(_ event: TaskLocalContextEvent, now: Date = Date()) -> TaskLocalContextEvent {
    ensureCurrentOwner()
    prune(now: now)
    if Self.learnableKinds.contains(event.kind) {
      currentContext = RecentContext(
        referenceHash: event.referenceHash,
        occurredAt: event.occurredAt
      )
    }
    if let subject = event.subject {
      bind(referenceHash: event.referenceHash, to: subject, now: now)
      return event
    }
    guard let entry = entries[event.referenceHash],
      let kind = OmiAPI.RecommendationSubjectKind(rawValue: entry.subjectKind),
      kind != ._unknown
    else { return event }
    return event.attaching(subject: TaskContextSubject(
      kind: kind,
      id: entry.subjectID,
      workstreamID: entry.workstreamID
    ))
  }

  func bindRecentContext(to subject: TaskContextSubject, now: Date = Date()) {
    ensureCurrentOwner()
    prune(now: now)
    guard let context = currentContext else { return }
    currentContext = nil
    guard now.timeIntervalSince(context.occurredAt) <= 90 else { return }
    bind(referenceHash: context.referenceHash, to: subject, now: now)
  }

  private func bind(referenceHash: String, to subject: TaskContextSubject, now: Date) {
    guard referenceHash.hasPrefix("sha256:") else { return }
    entries[referenceHash] = Entry(
      referenceHash: referenceHash,
      subjectKind: subject.kind.rawValue,
      subjectID: subject.id,
      workstreamID: subject.workstreamID,
      updatedAt: now
    )
    persist()
  }

  private func prune(now: Date) {
    let cutoff = now.addingTimeInterval(-30 * 24 * 60 * 60)
    entries = entries.filter { $0.value.updatedAt > cutoff }
    if entries.count > 256 {
      let keep = entries.values.sorted { $0.updatedAt > $1.updatedAt }.prefix(256)
      entries = Dictionary(uniqueKeysWithValues: keep.map { ($0.referenceHash, $0) })
    }
    persist()
  }

  private func persist() {
    defaults.set(
      try? JSONEncoder().encode(Array(entries.values)),
      forKey: .taskContextSubjectMatches(ownerHash: activeOwnerHash)
    )
  }

  private func ensureCurrentOwner() {
    guard fixedOwnerID == nil else { return }
    let next = Self.ownerHash(defaults.string(forKey: .authUserId) ?? "signed-out")
    guard next != activeOwnerHash else { return }
    activeOwnerHash = next
    currentContext = nil
    if let data = defaults.data(forKey: .taskContextSubjectMatches(ownerHash: activeOwnerHash)),
      let decoded = try? JSONDecoder().decode([Entry].self, from: data)
    {
      entries = Dictionary(uniqueKeysWithValues: decoded.map { ($0.referenceHash, $0) })
    } else {
      entries.removeAll()
    }
  }

  private static func ownerHash(_ owner: String) -> String {
    let digest = SHA256.hash(data: Data(owner.utf8)).map { String(format: "%02x", $0) }.joined()
    return String(digest.prefix(24))
  }

  private static let learnableKinds: Set<TaskContextEventKind> = [.person, .appWindow, .document]
}

struct TaskContextEventAccumulator {
  private(set) var eventsByKey: [String: [TaskLocalContextEvent]] = [:]

  mutating func insert(_ event: TaskLocalContextEvent, now: Date = Date()) {
    guard event.expiresAt > now else { return }
    var events = eventsByKey[event.coalescingKey, default: []]
    events.removeAll { $0.expiresAt <= now }
    if let index = events.firstIndex(where: {
      $0.kind == event.kind && $0.referenceHash == event.referenceHash && $0.subject == event.subject
    }) {
      events[index] = event
    } else {
      events.append(event)
    }
    eventsByKey[event.coalescingKey] = Array(events.suffix(16))
  }

  mutating func drain(now: Date = Date()) -> [TaskLocalContextEvent] {
    let result = eventsByKey.values.flatMap { $0 }.filter { $0.expiresAt > now }
    eventsByKey.removeAll()
    return result
  }

  var pendingWorkstreamCount: Int { eventsByKey.count }
}

enum TaskRecommendationEligibilityDenial: String, Equatable {
  case closed
  case expired
  case insufficientEvidence = "insufficient_evidence"
  case missingConcreteAction = "missing_concrete_action"
  case duplicate
}

struct TaskRecommendationEligibilityInput {
  let isOpen: Bool
  let expiresAt: Date
  let hasEvidence: Bool
  let hasConcreteAction: Bool
  let dedupeAlreadyActive: Bool
}

enum TaskRecommendationEligibility {
  static func denial(
    for input: TaskRecommendationEligibilityInput,
    now: Date
  ) -> TaskRecommendationEligibilityDenial? {
    if !input.isOpen { return .closed }
    if input.expiresAt <= now { return .expired }
    if !input.hasEvidence { return .insufficientEvidence }
    if !input.hasConcreteAction { return .missingConcreteAction }
    if input.dedupeAlreadyActive { return .duplicate }
    return nil
  }
}

enum ProactiveTaskCohort: String, Codable {
  case dogfood
  case beta
  case production

  static var current: Self {
    if AppBuild.isNonProduction { return .dogfood }
    return AppBuild.currentUpdateChannel == "beta" ? .beta : .production
  }
}

struct ProactiveTaskInterruptionConfiguration: Codable, Equatable {
  static let schemaVersion = 1
  static let safeDefault = ProactiveTaskInterruptionConfiguration(
    userOptedIn: false,
    shippedCohortsEnabled: false,
    dailyLimit: 2,
    minimumSpacing: 90 * 60,
    quietHoursStartMinute: 22 * 60,
    quietHoursEndMinute: 8 * 60,
    allowedPreparationKinds: []
  )

  let schemaVersion: Int
  var userOptedIn: Bool
  var shippedCohortsEnabled: Bool
  var dailyLimit: Int
  var minimumSpacing: TimeInterval
  var quietHoursStartMinute: Int
  var quietHoursEndMinute: Int
  var allowedPreparationKinds: Set<String>

  init(
    userOptedIn: Bool,
    shippedCohortsEnabled: Bool,
    dailyLimit: Int,
    minimumSpacing: TimeInterval,
    quietHoursStartMinute: Int,
    quietHoursEndMinute: Int,
    allowedPreparationKinds: Set<String>
  ) {
    self.schemaVersion = Self.schemaVersion
    self.userOptedIn = userOptedIn
    self.shippedCohortsEnabled = shippedCohortsEnabled
    self.dailyLimit = max(0, dailyLimit)
    self.minimumSpacing = max(0, minimumSpacing)
    self.quietHoursStartMinute = min(max(0, quietHoursStartMinute), 1439)
    self.quietHoursEndMinute = min(max(0, quietHoursEndMinute), 1439)
    self.allowedPreparationKinds = allowedPreparationKinds
  }

  func isEnrolled(cohort: ProactiveTaskCohort) -> Bool {
    guard userOptedIn else { return false }
    switch cohort {
    case .dogfood: return true
    case .beta, .production: return shippedCohortsEnabled
    }
  }
}

@MainActor
enum ProactiveTaskInterruptionSettings {
  static let configurationKey = "proactiveTaskInterruptionConfiguration.v1"
  static let focusSuppressedKey = "proactiveTaskInterruptionFocusSuppressed"

  static func load(defaults: UserDefaults = .standard) -> ProactiveTaskInterruptionConfiguration {
    guard let data = defaults.data(forKey: configurationKey),
      let config = try? JSONDecoder().decode(ProactiveTaskInterruptionConfiguration.self, from: data),
      config.schemaVersion == ProactiveTaskInterruptionConfiguration.schemaVersion
    else { return .safeDefault }
    return ProactiveTaskInterruptionConfiguration(
      userOptedIn: config.userOptedIn,
      shippedCohortsEnabled: config.shippedCohortsEnabled,
      dailyLimit: config.dailyLimit,
      minimumSpacing: config.minimumSpacing,
      quietHoursStartMinute: config.quietHoursStartMinute,
      quietHoursEndMinute: config.quietHoursEndMinute,
      allowedPreparationKinds: config.allowedPreparationKinds
    )
  }

  static func save(
    _ configuration: ProactiveTaskInterruptionConfiguration,
    defaults: UserDefaults = .standard
  ) {
    defaults.set(try? JSONEncoder().encode(configuration), forKey: configurationKey)
  }

  static var isFocusSuppressed: Bool {
    UserDefaults.standard.bool(forKey: focusSuppressedKey)
  }
}

struct TaskInterruptionCandidate: Equatable {
  let recommendationID: String
  let interventionID: String
  let dedupeKey: String
  let headline: String
  let whyNow: String
  let recommendedAction: String
  let expiresAt: Date
  let canWait: Bool
}

struct TaskInterruptionEnvironment {
  let cohort: ProactiveTaskCohort
  let masterNotificationsEnabled: Bool
  let frequencyEnabled: Bool
  let ambientFrequencyEligible: Bool
  let taskNotificationsEnabled: Bool
  let focusSuppressed: Bool
  let snoozed: Bool
  let now: Date
  let calendar: Calendar
}

enum TaskInterruptionGateReason: String, Codable, Equatable {
  case allowed
  case notEnrolled = "not_enrolled"
  case masterDisabled = "master_disabled"
  case frequencyDisabled = "frequency_disabled"
  case frequencyBudget = "frequency_budget"
  case taskDisabled = "task_disabled"
  case focusSuppressed = "focus_suppressed"
  case snoozed
  case quietHours = "quiet_hours"
  case expired
  case canWait = "can_wait"
  case duplicate
  case dailyBudget = "daily_budget"
  case minimumSpacing = "minimum_spacing"
}

struct TaskInterruptionGateTrace: Codable, Equatable {
  static let schemaVersion = 1
  let schemaVersion: Int
  let decisionID: String
  let recommendationID: String
  let interventionID: String
  let dedupeHash: String
  let cohort: ProactiveTaskCohort
  let reason: TaskInterruptionGateReason
  let evaluatedAt: Date

  init(candidate: TaskInterruptionCandidate, environment: TaskInterruptionEnvironment, reason: TaskInterruptionGateReason) {
    schemaVersion = Self.schemaVersion
    decisionID = "gate-\(UUID().uuidString.lowercased())"
    recommendationID = candidate.recommendationID
    interventionID = candidate.interventionID
    let hash = SHA256.hash(data: Data(candidate.dedupeKey.utf8))
      .map { String(format: "%02x", $0) }.joined()
    dedupeHash = "sha256:\(hash)"
    cohort = environment.cohort
    self.reason = reason
    evaluatedAt = environment.now
  }
}

struct TaskInterruptionLedger: Codable, Equatable {
  var sentAt: [Date] = []
  var dedupeExpirations: [String: Date] = [:]
  var lastTrace: TaskInterruptionGateTrace?
}

protocol TaskInterruptionLedgerPersisting: AnyObject {
  func load() -> TaskInterruptionLedger
  func save(_ ledger: TaskInterruptionLedger)
}

final class TaskInterruptionLedgerDefaults: TaskInterruptionLedgerPersisting {
  private let defaults: UserDefaults
  private let fixedOwnerID: String?

  init(defaults: UserDefaults = .standard, ownerID: String? = nil) {
    self.defaults = defaults
    fixedOwnerID = ownerID
  }

  private var key: String {
    let owner = fixedOwnerID ?? defaults.string(forKey: .authUserId) ?? "signed-out"
    return "proactiveTaskInterruptionLedger.v1.\(owner)"
  }

  func load() -> TaskInterruptionLedger {
    guard let data = defaults.data(forKey: key) else { return TaskInterruptionLedger() }
    return (try? JSONDecoder().decode(TaskInterruptionLedger.self, from: data)) ?? TaskInterruptionLedger()
  }

  func save(_ ledger: TaskInterruptionLedger) {
    defaults.set(try? JSONEncoder().encode(ledger), forKey: key)
  }
}

final class ProactiveTaskInterruptionGate {
  private let persistence: any TaskInterruptionLedgerPersisting

  init(persistence: any TaskInterruptionLedgerPersisting = TaskInterruptionLedgerDefaults()) {
    self.persistence = persistence
  }

  func evaluate(
    candidate: TaskInterruptionCandidate,
    configuration: ProactiveTaskInterruptionConfiguration,
    environment: TaskInterruptionEnvironment
  ) -> TaskInterruptionGateTrace {
    var ledger = persistence.load()
    ledger.sentAt.removeAll {
      environment.now.timeIntervalSince($0) >= max(48 * 60 * 60, configuration.minimumSpacing)
    }
    ledger.dedupeExpirations = ledger.dedupeExpirations.filter { $0.value > environment.now }
    let sentToday = ledger.sentAt.filter {
      environment.calendar.isDate($0, inSameDayAs: environment.now)
    }.count

    let reason: TaskInterruptionGateReason
    if !configuration.isEnrolled(cohort: environment.cohort) { reason = .notEnrolled }
    else if !environment.masterNotificationsEnabled { reason = .masterDisabled }
    else if !environment.frequencyEnabled { reason = .frequencyDisabled }
    else if !environment.taskNotificationsEnabled { reason = .taskDisabled }
    else if environment.focusSuppressed { reason = .focusSuppressed }
    else if environment.snoozed { reason = .snoozed }
    else if Self.isQuietHours(configuration: configuration, environment: environment) { reason = .quietHours }
    else if candidate.expiresAt <= environment.now { reason = .expired }
    else if candidate.canWait { reason = .canWait }
    else if ledger.dedupeExpirations[candidate.dedupeKey] != nil { reason = .duplicate }
    else if !environment.ambientFrequencyEligible { reason = .frequencyBudget }
    else if sentToday >= configuration.dailyLimit { reason = .dailyBudget }
    else if let last = ledger.sentAt.max(),
      environment.now.timeIntervalSince(last) < configuration.minimumSpacing
    { reason = .minimumSpacing }
    else { reason = .allowed }

    let trace = TaskInterruptionGateTrace(candidate: candidate, environment: environment, reason: reason)
    ledger.lastTrace = trace
    if reason == .allowed {
      ledger.sentAt.append(environment.now)
      ledger.dedupeExpirations[candidate.dedupeKey] = candidate.expiresAt
    }
    persistence.save(ledger)
    return trace
  }

  private static func isQuietHours(
    configuration: ProactiveTaskInterruptionConfiguration,
    environment: TaskInterruptionEnvironment
  ) -> Bool {
    let components = environment.calendar.dateComponents([.hour, .minute], from: environment.now)
    let minute = (components.hour ?? 0) * 60 + (components.minute ?? 0)
    let start = configuration.quietHoursStartMinute
    let end = configuration.quietHoursEndMinute
    if start == end { return false }
    if start < end { return minute >= start && minute < end }
    return minute >= start || minute < end
  }
}

struct ProactiveTaskArtifactProposal {
  let workstreamID: String
  let logicalKey: String
  let kind: String
  let content: Data
  let evidenceRefs: [OmiAPI.EvidenceRef]
  let executionReady: Bool
  let coordinatorGrantID: String?

  init(
    workstreamID: String,
    logicalKey: String,
    kind: String,
    content: Data,
    evidenceRefs: [OmiAPI.EvidenceRef],
    executionReady: Bool,
    coordinatorGrantID: String?
  ) {
    self.workstreamID = workstreamID
    self.logicalKey = logicalKey
    self.kind = kind
    self.content = content
    self.evidenceRefs = Array(evidenceRefs.prefix(20))
    self.executionReady = executionReady
    self.coordinatorGrantID = coordinatorGrantID
  }
}

enum ProactiveTaskPreparationDenial: String, Equatable {
  case kindNotAllowed = "kind_not_allowed"
  case notExecutionReady = "not_execution_ready"
  case missingCoordinatorGrant = "missing_coordinator_grant"
  case missingEvidence = "missing_evidence"
  case emptyContent = "empty_content"
}

enum ProactiveTaskPreparationPolicy {
  static func denial(
    proposal: ProactiveTaskArtifactProposal,
    configuration: ProactiveTaskInterruptionConfiguration
  ) -> ProactiveTaskPreparationDenial? {
    if !configuration.allowedPreparationKinds.contains(proposal.kind) { return .kindNotAllowed }
    if !proposal.executionReady { return .notExecutionReady }
    if proposal.coordinatorGrantID?.isEmpty != false { return .missingCoordinatorGrant }
    if proposal.evidenceRefs.isEmpty { return .missingEvidence }
    if proposal.content.isEmpty { return .emptyContent }
    return nil
  }
}

struct KernelPreparedArtifactReceipt {
  let version: Int
  let supersedesArtifactID: String?
  let contentHash: String
  let fileURL: URL
  let deliveryIDs: [String]
}

/// Writes one hash-addressed payload, then delegates session binding, immutable
/// versioning, supersession, and delivery receipts to the Ticket-06 kernel.
@MainActor
final class KernelPreparedArtifactBridge {
  typealias Persist = @MainActor (
    _ workstreamID: String,
    _ logicalKey: String,
    _ kind: String,
    _ fileURL: URL,
    _ contentHash: String,
    _ evidenceRefs: [OmiAPI.EvidenceRef],
    _ grantID: String
  ) async throws -> TaskKernelPreparedArtifactReceipt

  private let root: URL
  private let fileManager: FileManager
  private let persist: Persist

  init(
    root: URL? = nil,
    fileManager: FileManager = .default,
    persist: @escaping Persist = { workstreamID, logicalKey, kind, fileURL, contentHash, evidenceRefs, grantID in
      try await TaskWorkstreamContinuity.persistPreparedArtifact(
        workstreamId: workstreamID,
        logicalKey: logicalKey,
        kind: kind,
        fileURL: fileURL,
        contentHash: contentHash,
        evidenceRefs: evidenceRefs,
        grantId: grantID
      )
    }
  ) {
    self.fileManager = fileManager
    self.persist = persist
    if let root {
      self.root = root
    } else {
      let owner = UserDefaults.standard.string(forKey: .authUserId) ?? "signed-out"
      let ownerHash = SHA256.hash(data: Data(owner.utf8))
        .map { String(format: "%02x", $0) }.joined()
      self.root = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("Omi/PreparedTaskArtifacts", isDirectory: true)
        .appendingPathComponent(Self.safeComponent(AppBuild.bundleIdentifier), isDirectory: true)
        .appendingPathComponent(String(ownerHash.prefix(24)), isDirectory: true)
    }
  }

  func prepare(
    _ proposal: ProactiveTaskArtifactProposal,
    configuration: ProactiveTaskInterruptionConfiguration
  ) async throws -> KernelPreparedArtifactReceipt? {
    guard ProactiveTaskPreparationPolicy.denial(proposal: proposal, configuration: configuration) == nil else {
      return nil
    }
    let digest = SHA256.hash(data: proposal.content).map { String(format: "%02x", $0) }.joined()
    let contentHash = "sha256:\(digest)"
    let payloadDirectory = root.appendingPathComponent("payloads", isDirectory: true)
    try fileManager.createDirectory(at: payloadDirectory, withIntermediateDirectories: true)
    let fileURL = payloadDirectory.appendingPathComponent("\(digest).artifact")
    if !fileManager.fileExists(atPath: fileURL.path) {
      try proposal.content.write(to: fileURL, options: .withoutOverwriting)
    }
    let continuity = try await persist(
      proposal.workstreamID,
      Self.safeComponent(proposal.logicalKey),
      proposal.kind,
      fileURL,
      contentHash,
      proposal.evidenceRefs,
      proposal.coordinatorGrantID!
    )
    let version = continuity.artifactVersion
    guard version.logicalKey == Self.safeComponent(proposal.logicalKey),
      version.artifact.contentHash == contentHash
    else { throw TaskWorkstreamContinuityError.invalidRuntimeResponse }
    return KernelPreparedArtifactReceipt(
      version: version.version,
      supersedesArtifactID: version.supersedesArtifactId,
      contentHash: contentHash,
      fileURL: fileURL,
      deliveryIDs: continuity.deliveries.map(\.deliveryId)
    )
  }

  private static func safeComponent(_ value: String) -> String {
    let mapped = value.lowercased().map { $0.isLetter || $0.isNumber ? $0 : "-" }
    let collapsed = String(mapped).replacingOccurrences(of: "-+", with: "-", options: .regularExpression)
      .trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    return String((collapsed.isEmpty ? "artifact" : collapsed).prefix(96))
  }
}

protocol TaskContextualResurfacingClient: AnyObject {
  func getCandidateWorkflowControl() async throws -> OmiAPI.TaskWorkflowControl
  func replaceTaskContextSnapshot(
    _ snapshot: OmiAPI.NormalizedContextSnapshot,
    accountGeneration: Int
  ) async throws -> OmiAPI.SnapshotReceipt
  func evaluateWhatMattersNow(_ request: OmiAPI.EvaluationRequest) async throws -> OmiAPI.WhatMattersNowProjection
}

extension APIClient: TaskContextualResurfacingClient {}

extension Notification.Name {
  static let whatMattersNowContextDidRefresh = Notification.Name("whatMattersNowContextDidRefresh")
  static let openWhatMattersNowRecommendation = Notification.Name("openWhatMattersNowRecommendation")
}

/// Persistent navigation owner for notification clicks. The dashboard view is
/// intentionally recreated on tab changes, so it cannot own the pending route.
@MainActor
final class ContextualTaskNavigationRouter {
  static let shared = ContextualTaskNavigationRouter()
  private(set) var pendingRecommendationID: String?

  func request(recommendationID: String) {
    guard !recommendationID.isEmpty else { return }
    pendingRecommendationID = recommendationID
    NotificationCenter.default.post(name: .navigateToChat, object: nil)
    DispatchQueue.main.async {
      NotificationCenter.default.post(
        name: .openWhatMattersNowRecommendation,
        object: nil,
        userInfo: [TaskContextualResurfacingService.recommendationIDUserInfoKey: recommendationID]
      )
    }
  }

  func consume(requestedID: String? = nil) -> String? {
    guard let pendingRecommendationID else { return nil }
    if let requestedID, requestedID != pendingRecommendationID { return nil }
    self.pendingRecommendationID = nil
    return pendingRecommendationID
  }
}

actor TaskContextualResurfacingService {
  static let shared = TaskContextualResurfacingService()
  static let recommendationIDUserInfoKey = "recommendation_id"

  private let client: any TaskContextualResurfacingClient
  private let debounceInterval: TimeInterval
  private var accumulator = TaskContextEventAccumulator()
  private var debounceTask: Task<Void, Never>?
  private var lastMaterialHint: String?
  private var lastEvaluationAt: Date?

  init(
    client: any TaskContextualResurfacingClient = APIClient.shared,
    debounceInterval: TimeInterval = 2
  ) {
    self.client = client
    self.debounceInterval = debounceInterval
  }

  func observe(_ event: TaskLocalContextEvent) {
    accumulator.insert(event)
    debounceTask?.cancel()
    debounceTask = Task { [weak self] in
      guard let self else { return }
      let nanos = UInt64(max(0, self.debounceInterval) * 1_000_000_000)
      try? await Task.sleep(nanoseconds: nanos)
      guard !Task.isCancelled else { return }
      await self.flush()
    }
  }

  func pendingWorkstreamCount() -> Int { accumulator.pendingWorkstreamCount }

  func flush() async {
    debounceTask?.cancel()
    debounceTask = nil
    let now = Date()
    let events = accumulator.drain(now: now)
    guard !events.isEmpty else { return }
    let materialFingerprint = events.map { event in
      [
        event.kind.rawValue,
        event.referenceHash,
        event.subject?.kind.rawValue ?? "none",
        event.subject?.id ?? "none",
        event.urgency.rawValue,
      ].joined(separator: "|")
    }.sorted().joined(separator: "||")
    let materialHash = SHA256.hash(data: Data(materialFingerprint.utf8))
      .map { String(format: "%02x", $0) }.joined()
    let materialHint = "ctx:\(materialHash.prefix(32))"
    if lastMaterialHint == materialHint,
      let lastEvaluationAt,
      now.timeIntervalSince(lastEvaluationAt) < 5 * 60
    {
      return
    }
    do {
      let control = try await client.getCandidateWorkflowControl()
      guard control.workflowMode == .read, let accountGeneration = control.accountGeneration else { return }
      let deviceID = ClientDeviceService.shared.deviceIdHash
      let matches = Self.contextMatches(events)
      let snapshot = OmiAPI.NormalizedContextSnapshot(
        deviceId: deviceID,
        expiresAt: Self.iso8601(now.addingTimeInterval(5 * 60)),
        generatedAt: Self.iso8601(now),
        matches: matches,
        schemaVersion: 1,
        snapshotId: "ctx-\(UUID().uuidString.lowercased())"
      )
      _ = try await client.replaceTaskContextSnapshot(
        snapshot,
        accountGeneration: accountGeneration
      )
      let projection = try await client.evaluateWhatMattersNow(
        OmiAPI.EvaluationRequest(deviceId: deviceID, materialHint: materialHint)
      )
      lastMaterialHint = materialHint
      lastEvaluationAt = now
      await MainActor.run {
        NotificationCenter.default.post(name: .whatMattersNowContextDidRefresh, object: projection)
      }
      await interruptIfEligible(projection: projection, events: events, now: now)
    } catch {
      logError("TaskContextualResurfacing: context re-evaluation failed", error: error)
    }
  }

  private func interruptIfEligible(
    projection: OmiAPI.WhatMattersNowProjection,
    events: [TaskLocalContextEvent],
    now: Date
  ) async {
    let urgentSubjects = Set(events.filter { $0.urgency == .timeSensitive }.compactMap(\.subject))
    guard !urgentSubjects.isEmpty else { return }
    guard let recommendation = projection.recommendations.first(where: { item in
      urgentSubjects.contains(TaskContextSubject(
        kind: item.subjectKind,
        id: item.subjectId,
        workstreamID: item.destinationWorkstreamId
      ))
    }) else { return }
    guard let expiresAt = Self.parseDate(recommendation.expiresAt) else { return }
    let candidate = TaskInterruptionCandidate(
      recommendationID: "\(recommendation.outputVersion):\(recommendation.dedupeKey)",
      interventionID: recommendation.interventionId,
      dedupeKey: recommendation.dedupeKey,
      headline: recommendation.headline,
      whyNow: recommendation.whyNow,
      recommendedAction: recommendation.recommendedAction,
      expiresAt: expiresAt,
      canWait: false
    )
    _ = await MainActor.run {
      NotificationService.shared.sendContextualTaskInterruption(candidate)
    }
  }

  private static func contextMatches(_ events: [TaskLocalContextEvent]) -> [OmiAPI.NormalizedContextMatch] {
    let grouped = Dictionary(grouping: events.compactMap { event -> (TaskContextSubject, OmiAPI.ContextMatchSignal)? in
      guard let subject = event.subject, let signal = event.kind.recommendationSignal else { return nil }
      return (subject, signal)
    }, by: \.0)
    return grouped.map { subject, entries in
      let signals = Dictionary(entries.map { ($0.1.rawValue, $0.1) }, uniquingKeysWith: { first, _ in first })
        .values.sorted { $0.rawValue < $1.rawValue }
      return OmiAPI.NormalizedContextMatch(signals: signals, subjectId: subject.id, subjectKind: subject.kind)
    }.sorted { ($0.subjectKind.rawValue, $0.subjectId) < ($1.subjectKind.rawValue, $1.subjectId) }
  }

  private static func iso8601(_ date: Date) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: date)
  }

  private static func parseDate(_ value: String) -> Date? {
    let precise = ISO8601DateFormatter()
    precise.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return precise.date(from: value) ?? ISO8601DateFormatter().date(from: value)
  }
}
