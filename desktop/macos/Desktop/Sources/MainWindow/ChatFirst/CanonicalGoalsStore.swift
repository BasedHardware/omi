import Combine
import Foundation

/// The narrow canonical-goal contract shared by the cohort-only Chat renderers
/// and Goals destination. It intentionally has no relationship to the
/// Dashboard recommendation/outbox state.
protocol CanonicalGoalsClient: AnyObject {
  func getCanonicalGoals(
    includeEnded: Bool,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> [OmiAPI.GoalResponse]
  func getCanonicalGoalDetail(
    goalID: String,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.GoalDetailProjection
  func focusCanonicalGoal(
    goalID: String,
    replacementGoalID: String?,
    focusRank: Int?,
    accountGeneration: Int,
    idempotencyKey: String,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.GoalResponse
}

extension APIClient: CanonicalGoalsClient {}

/// Root-owned canonical projection for the chat-first cohort. The store accepts
/// only the immutable capability sampled by the root shell; it never reads a
/// local rollout preference or re-decides the cohort from cached goal data.
@MainActor
final class CanonicalGoalsStore: ObservableObject {
  enum Availability: Equatable {
    case inactive
    case loading
    case ready
    case unavailable(String)
  }

  private struct Scope: Equatable {
    let ownerID: String
    let authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
    let capability: ChatFirstCapabilityProjection
    let revision: UInt
  }

  @Published private(set) var goals: [OmiAPI.GoalResponse] = []
  @Published private(set) var selectedGoalDetail: OmiAPI.GoalDetailProjection?
  @Published private(set) var availability: Availability = .inactive
  @Published private(set) var error: String?
  @Published private(set) var focusMutationGoalID: String?

  private let client: any CanonicalGoalsClient
  private let ownerIDProvider: () -> String?
  private let authorizationSnapshotProvider: (String) -> RuntimeOwnerAuthorizationSnapshot?
  private var capability: ChatFirstCapabilityProjection?
  private var ownerID: String?
  private var ownerRevision: UInt = 0
  private var activeLoadToken: UUID?

  init(
    client: any CanonicalGoalsClient = APIClient.shared,
    ownerIDProvider: @escaping () -> String? = { RuntimeOwnerIdentity.currentOwnerId() },
    authorizationSnapshotProvider: @escaping (String) -> RuntimeOwnerAuthorizationSnapshot? = {
      RuntimeOwnerIdentity.captureAuthorizationSnapshot(expectedOwnerID: $0)
    }
  ) {
    self.client = client
    self.ownerIDProvider = ownerIDProvider
    self.authorizationSnapshotProvider = authorizationSnapshotProvider
  }

  var isLoading: Bool {
    if case .loading = availability { return true }
    return false
  }

  var primaryFocusedGoal: OmiAPI.GoalResponse? {
    focusedGoals.first
  }

  var focusedGoals: [OmiAPI.GoalResponse] {
    activeGoals
      .filter { $0.status == .focused }
      .sorted { ($0.focusRank ?? Int.max, $0.updatedAt) < ($1.focusRank ?? Int.max, $1.updatedAt) }
  }

  var activeGoals: [OmiAPI.GoalResponse] {
    goals
      .filter { $0.isActive && $0.status != .achieved && $0.status != .abandoned }
      .sorted { ($0.focusRank ?? Int.max, $0.updatedAt) < ($1.focusRank ?? Int.max, $1.updatedAt) }
  }

  var otherActiveGoals: [OmiAPI.GoalResponse] {
    let primaryID = primaryFocusedGoal?.goalId
    return activeGoals.filter { $0.goalId != primaryID }
  }

  /// Called exclusively by `ChatFirstShell` with its one app-session sample.
  /// A changed/missing owner fails closed to an unavailable projection rather
  /// than letting a new account consume a previous account's goal state.
  func activate(capability: ChatFirstCapabilityProjection) {
    guard capability.chatFirstUi,
      let normalizedOwnerID = normalized(ownerIDProvider())
    else {
      deactivateAsUnavailable()
      return
    }

    if let existingCapability = self.capability, let ownerID {
      guard existingCapability == capability, ownerID == normalizedOwnerID else {
        deactivateAsUnavailable()
        return
      }
      return
    }

    self.capability = capability
    ownerID = normalizedOwnerID
    ownerRevision &+= 1
    goals = []
    selectedGoalDetail = nil
    error = nil
    availability = .inactive
  }

  func resetSessionState() {
    capability = nil
    ownerID = nil
    ownerRevision &+= 1
    activeLoadToken = nil
    goals = []
    selectedGoalDetail = nil
    focusMutationGoalID = nil
    error = nil
    availability = .inactive
  }

  func load() async {
    guard let scope = captureScope() else { return }
    guard activeLoadToken == nil else { return }

    let token = UUID()
    activeLoadToken = token
    error = nil
    availability = .loading
    defer {
      if activeLoadToken == token {
        activeLoadToken = nil
      }
    }

    do {
      let loadedGoals = try await client.getCanonicalGoals(
        includeEnded: false,
        expectedOwnerId: scope.ownerID,
        authorizationSnapshot: scope.authorizationSnapshot
      )
      guard scopeIsCurrent(scope), activeLoadToken == token else { return }
      goals = loadedGoals
      availability = .ready
    } catch {
      guard scopeIsCurrent(scope), activeLoadToken == token else { return }
      goals = []
      selectedGoalDetail = nil
      let message = "Goals are unavailable right now. Try again."
      self.error = message
      availability = .unavailable(message)
    }
  }

  /// Fetching detail is also the ownership/deletion validation boundary for a
  /// journaled goal link. The result is display data only; task mutations stay
  /// in `TasksStore`.
  @discardableResult
  func loadDetail(goalID: String) async -> OmiAPI.GoalDetailProjection? {
    guard let scope = captureScope(), let normalizedGoalID = normalized(goalID) else { return nil }
    do {
      let detail = try await client.getCanonicalGoalDetail(
        goalID: normalizedGoalID,
        expectedOwnerId: scope.ownerID,
        authorizationSnapshot: scope.authorizationSnapshot
      )
      guard scopeIsCurrent(scope), detail.goal.goalId == normalizedGoalID else { return nil }
      selectedGoalDetail = detail
      if case .unavailable = availability {
        // A confirmed canonical detail is enough to let a deep link render its
        // target while the list can be retried independently.
        availability = .ready
      }
      error = nil
      return detail
    } catch {
      guard scopeIsCurrent(scope) else { return nil }
      // A missing/revoked target must remain an inert link or an honest page
      // state; do not substitute a legacy-goal record.
      selectedGoalDetail = nil
      self.error = "This goal is no longer available."
      return nil
    }
  }

  /// Focus is a server mutation with the root-sampled generation and an
  /// occurrence-specific idempotency key. The page always reconciles the full
  /// projection afterwards instead of locally reordering an optimistic list.
  @discardableResult
  func setAsFocus(goalID: String) async -> Bool {
    guard let scope = captureScope(), let normalizedGoalID = normalized(goalID) else { return false }
    guard activeGoals.contains(where: { $0.goalId == normalizedGoalID }) else {
      error = "This goal is no longer available."
      return false
    }
    if primaryFocusedGoal?.goalId == normalizedGoalID { return true }
    guard focusMutationGoalID == nil else { return false }

    let replacementGoalID = primaryFocusedGoal?.goalId
    focusMutationGoalID = normalizedGoalID
    defer { focusMutationGoalID = nil }
    do {
      _ = try await client.focusCanonicalGoal(
        goalID: normalizedGoalID,
        replacementGoalID: replacementGoalID,
        focusRank: nil,
        accountGeneration: scope.capability.controlGeneration,
        idempotencyKey: "goal-focus:\(normalizedGoalID):\(UUID().uuidString.lowercased())",
        expectedOwnerId: scope.ownerID,
        authorizationSnapshot: scope.authorizationSnapshot
      )
      guard scopeIsCurrent(scope) else { return false }
      await load()
      guard scopeIsCurrent(scope) else { return false }
      return true
    } catch {
      guard scopeIsCurrent(scope) else { return false }
      self.error = "Goal focus could not be updated."
      return false
    }
  }

  private func captureScope() -> Scope? {
    guard let capability, let ownerID, normalized(ownerIDProvider()) == ownerID else {
      deactivateAsUnavailable()
      return nil
    }
    return Scope(
      ownerID: ownerID,
      authorizationSnapshot: authorizationSnapshotProvider(ownerID),
      capability: capability,
      revision: ownerRevision
    )
  }

  private func scopeIsCurrent(_ scope: Scope) -> Bool {
    scope.ownerID == ownerID
      && scope.capability == capability
      && scope.revision == ownerRevision
      && normalized(ownerIDProvider()) == scope.ownerID
      && (scope.authorizationSnapshot.map(RuntimeOwnerIdentity.isAuthorizationCurrent) ?? true)
      && !Task.isCancelled
  }

  private func deactivateAsUnavailable() {
    capability = nil
    ownerID = nil
    ownerRevision &+= 1
    activeLoadToken = nil
    goals = []
    selectedGoalDetail = nil
    focusMutationGoalID = nil
    let message = "Goals are unavailable right now. Try again."
    error = message
    availability = .unavailable(message)
  }

  private func normalized(_ value: String?) -> String? {
    guard let value else { return nil }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return normalized.isEmpty ? nil : normalized
  }
}

/// Pure detail presentation rules keep generated aggregate task records as
/// display references. They are never converted into mutable task models.
enum ChatFirstGoalDetailPolicy {
  static func completedTaskCount(in detail: OmiAPI.GoalDetailProjection) -> Int {
    detail.tasks.count(where: \.completed)
  }

  static func nextTaskIDs(in detail: OmiAPI.GoalDetailProjection, limit: Int = 3) -> [String] {
    detail.tasks
      .filter { !$0.completed }
      .prefix(max(0, limit))
      .map(\.id)
  }

  static func focusToAcknowledge(
    pendingFocus: ChatFirstPendingFocus?,
    visibleGoalID: String
  ) -> ChatFirstPendingFocus? {
    guard case .goal(let goalID) = pendingFocus, goalID == visibleGoalID else { return nil }
    return pendingFocus
  }
}
