import AppKit
import Foundation

enum JITTriggerFeedbackAction: String, Codable, Sendable {
  case useful
  case falsePositive = "false_positive"
  case snooze
  case disable
  case missedOrLate = "missed_or_late"

  var interjectVerb: InterjectFeedbackVerb {
    switch self {
    case .useful: return .useful
    case .falsePositive: return .falsePositive
    case .snooze: return .snooze
    case .disable: return .disable
    case .missedOrLate: return .missed
    }
  }
}

/// Opaque identifiers carried from a planned trigger to its notification
/// controls. The UI never receives trigger text or screen evidence.
struct JITTriggerFeedbackContext: Equatable, Sendable {
  let ownerID: String
  let eventID: String
  let triggerMemoryID: String
  let accountGeneration: Int
  let triggerRevision: Int
}

struct JITTriggerFeedback: Codable, Equatable, Sendable {
  let feedbackID: String
  let eventID: String
  let triggerMemoryID: String
  let accountGeneration: Int
  let triggerRevision: Int
  let action: JITTriggerFeedbackAction
  let recordedAt: Date
  let snoozedUntil: Date?

  init(
    feedbackID: String,
    eventID: String,
    triggerMemoryID: String,
    accountGeneration: Int,
    triggerRevision: Int,
    action: JITTriggerFeedbackAction,
    recordedAt: Date = Date(),
    snoozedUntil: Date? = nil
  ) {
    self.feedbackID = feedbackID
    self.eventID = eventID
    self.triggerMemoryID = triggerMemoryID
    self.accountGeneration = accountGeneration
    self.triggerRevision = triggerRevision
    self.action = action
    self.recordedAt = recordedAt
    self.snoozedUntil = snoozedUntil
  }
}

private struct JITTriggerFeedbackRequest: Encodable {
  let feedbackID: String
  let eventID: String
  let triggerMemoryID: String
  let accountGeneration: Int
  let triggerRevision: Int
  let action: JITTriggerFeedbackAction
  let recordedAt: Date
  let snoozedUntil: Date?

  enum CodingKeys: String, CodingKey {
    case feedbackID = "feedback_id"
    case eventID = "event_id"
    case triggerMemoryID = "trigger_memory_id"
    case accountGeneration = "account_generation"
    case triggerRevision = "trigger_revision"
    case action
    case recordedAt = "recorded_at"
    case snoozedUntil = "snoozed_until"
  }
}

private struct JITTriggerFeedbackResponse: Decodable {
  let applied: Bool
}

/// UserDefaults itself is not Sendable, but this client owns the reference and
/// serializes every access on its actor. The wrapper makes that ownership
/// explicit for injected test suites as well as the standard store.
final class JITTriggerFeedbackDefaults: @unchecked Sendable {
  let value: UserDefaults

  init(_ value: UserDefaults) {
    self.value = value
  }

  static let standard = JITTriggerFeedbackDefaults(.standard)
}

/// Explicit-only feedback transport. The queue stores identifiers and
/// bounded timestamps, never notification text or screen evidence. A failed
/// upload remains queued for a later retry; silence is never interpreted as a
/// negative signal.
actor JITTriggerFeedbackClient {
  static let shared = JITTriggerFeedbackClient()
  private static let defaultsKey = "jit.triggerFeedbackOutbox.v1"
  private let defaults: UserDefaults
  private let submitter: @Sendable (JITTriggerFeedback, RuntimeOwnerAuthorizationSnapshot) async -> Bool
  private let authorizationCurrent: @Sendable (RuntimeOwnerAuthorizationSnapshot) -> Bool
  private let authorizationSnapshotProvider: @Sendable () -> RuntimeOwnerAuthorizationSnapshot?
  private var lifecycleObservers: [NSObjectProtocol] = []
  private var retryTask: Task<Void, Never>?
  private var flushingOwners = Set<String>()

  init(
    defaults: JITTriggerFeedbackDefaults = .standard,
    submitter: @escaping @Sendable (JITTriggerFeedback, RuntimeOwnerAuthorizationSnapshot) async -> Bool = {
      feedback,
      authorizationSnapshot in
      let body = JITTriggerFeedbackRequest(
        feedbackID: feedback.feedbackID,
        eventID: feedback.eventID,
        triggerMemoryID: feedback.triggerMemoryID,
        accountGeneration: feedback.accountGeneration,
        triggerRevision: feedback.triggerRevision,
        action: feedback.action,
        recordedAt: feedback.recordedAt,
        snoozedUntil: feedback.snoozedUntil)
      do {
        let _: JITTriggerFeedbackResponse = try await APIClient.shared.post(
          "v1/jit/trigger-feedback",
          body: body,
          authorizationSnapshot: authorizationSnapshot)
        return true
      } catch {
        return false
      }
    },
    authorizationCurrent: @escaping @Sendable (RuntimeOwnerAuthorizationSnapshot) -> Bool =
      RuntimeOwnerIdentity.isAuthorizationCurrent,
    authorizationSnapshotProvider: @escaping @Sendable () -> RuntimeOwnerAuthorizationSnapshot? =
      { RuntimeOwnerIdentity.captureAuthorizationSnapshot() }
  ) {
    self.defaults = defaults.value
    self.submitter = submitter
    self.authorizationCurrent = authorizationCurrent
    self.authorizationSnapshotProvider = authorizationSnapshotProvider
  }

  /// Starts the process-lifetime retry loop. It is intentionally independent
  /// of a later feedback button: launch, auth restoration, app activation, and
  /// transient network recovery all get a chance to drain the durable queue.
  func installLifecycleRetry() {
    guard lifecycleObservers.isEmpty else { return }
    let center = NotificationCenter.default
    lifecycleObservers = [
      center.addObserver(forName: .runtimeOwnerDidChange, object: nil, queue: nil) {
        [weak self] _ in
        Task { await self?.flushForCurrentOwner() }
      },
      center.addObserver(forName: NSApplication.didBecomeActiveNotification, object: nil, queue: nil) {
        [weak self] _ in
        Task { await self?.flushForCurrentOwner() }
      },
    ]
    retryTask = Task { [weak self] in
      while !Task.isCancelled {
        await self?.flushForCurrentOwner()
        // A short bounded poll is the recovery path for a network that comes
        // back without an app/auth lifecycle notification.
        try? await Task.sleep(nanoseconds: 30_000_000_000)
      }
    }
    Task { await flushForCurrentOwner() }
  }

  private func flushForCurrentOwner() async {
    guard let authorizationSnapshot = authorizationSnapshotProvider() else { return }
    await flush(authorizationSnapshot: authorizationSnapshot)
  }

  func record(
    _ feedback: JITTriggerFeedback,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async {
    guard valid(feedback), authorizationCurrent(authorizationSnapshot) else { return }
    let owner = authorizationSnapshot.ownerID
    var pending = load(ownerID: owner)
    if !pending.contains(where: { $0.feedbackID == feedback.feedbackID }) {
      pending.append(feedback)
      save(pending, ownerID: owner)
    }
    await flush(authorizationSnapshot: authorizationSnapshot)
  }

  func flush(authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot) async {
    guard authorizationCurrent(authorizationSnapshot) else { return }
    let owner = authorizationSnapshot.ownerID
    guard flushingOwners.insert(owner).inserted else { return }
    defer { flushingOwners.remove(owner) }

    // Reload after every awaited submission. Actor isolation protects the
    // mutation itself, but the submitter await permits record() to append a
    // later action; removing from a stale array would otherwise overwrite it.
    while let feedback = load(ownerID: owner).first {
      guard valid(feedback) else {
        var current = load(ownerID: owner)
        current.removeAll { $0.feedbackID == feedback.feedbackID }
        save(current, ownerID: owner)
        continue
      }
      guard await submitter(feedback, authorizationSnapshot) else {
        // Keep the head item for retry. Do not infer feedback from this
        // failure, and do not drop later explicit actions behind it.
        return
      }
      var current = load(ownerID: owner)
      current.removeAll { $0.feedbackID == feedback.feedbackID }
      save(current, ownerID: owner)
    }
  }

  func pendingCount(ownerID: String) -> Int {
    load(ownerID: ownerID).count
  }

  func pendingFeedbackIDs(ownerID: String) -> [String] {
    load(ownerID: ownerID).map(\.feedbackID)
  }

  private func valid(_ feedback: JITTriggerFeedback) -> Bool {
    JITProactivityReservation.isIdentifier(feedback.feedbackID)
      && JITProactivityReservation.isIdentifier(feedback.eventID)
      && !feedback.triggerMemoryID.isEmpty
      && !feedback.triggerMemoryID.contains("/")
      && feedback.triggerMemoryID.count <= 256
      && feedback.accountGeneration >= 0
      && feedback.triggerRevision > 0
      && (feedback.action == .snooze) == (feedback.snoozedUntil != nil)
      && (feedback.snoozedUntil.map { $0 > feedback.recordedAt } ?? true)
  }

  private func storageKey(ownerID: String) -> String {
    "\(Self.defaultsKey).\(JITProactivityReservation.identifier("owner", ownerID))"
  }

  private func load(ownerID: String) -> [JITTriggerFeedback] {
    guard let data = defaults.data(forKey: storageKey(ownerID: ownerID)) else { return [] }
    return (try? JSONDecoder().decode([JITTriggerFeedback].self, from: data)) ?? []
  }

  private func save(_ feedback: [JITTriggerFeedback], ownerID: String) {
    guard let data = try? JSONEncoder().encode(feedback) else { return }
    defaults.set(data, forKey: storageKey(ownerID: ownerID))
  }
}
