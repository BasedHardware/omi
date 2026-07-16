import Foundation

protocol DashboardIntelligenceClient: AnyObject, Sendable {
  func getCandidateWorkflowControl() async throws -> OmiAPI.TaskWorkflowControl
  func getWhatMattersNow(deviceID: String?) async throws -> OmiAPI.WhatMattersNowProjection
  func getCanonicalGoals(includeEnded: Bool) async throws -> [OmiAPI.GoalResponse]
  func getCanonicalGoalDetail(goalID: String) async throws -> OmiAPI.GoalDetailProjection
  func getCanonicalCandidate(candidateID: String) async throws -> OmiAPI.CandidateRecord
  func getActionItem(id: String) async throws -> TaskActionItem
  func createCanonicalGoal(
    title: String, desiredOutcome: String, whyItMatters: String?, successCriteria: [String],
    accountGeneration: Int, idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse
  func recordTaskFeedback(
    _ request: OmiAPI.FeedbackCreate, idempotencyKey: String, accountGeneration: Int
  ) async throws -> OmiAPI.FeedbackRecord
  func createTaskOutcome(
    _ request: OmiAPI.OutcomeCreate, idempotencyKey: String, accountGeneration: Int
  ) async throws -> OmiAPI.OutcomeRecord
  func focusCanonicalGoal(
    goalID: String, replacementGoalID: String?, focusRank: Int?, accountGeneration: Int,
    idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse
  func unfocusCanonicalGoal(
    goalID: String, accountGeneration: Int, idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse
  func transitionCanonicalGoal(
    goalID: String, status: OmiAPI.GoalStatus, relationshipDisposition: String,
    accountGeneration: Int, idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse
}

extension APIClient: @preconcurrency DashboardIntelligenceClient {}

@MainActor
final class TaskNavigationRequestStore {
  static let shared = TaskNavigationRequestStore()
  enum Target: Equatable {
    case task(String)
    case candidate(String)
  }

  private(set) var pendingTarget: Target?
  private(set) var pendingTask: TaskActionItem?
  private(set) var pendingCandidate: OmiAPI.CandidateRecord?

  func request(task: TaskActionItem) {
    pendingTarget = .task(task.id)
    pendingTask = task
    pendingCandidate = nil
  }

  func request(candidate: OmiAPI.CandidateRecord) {
    pendingTarget = .candidate(candidate.candidateId)
    pendingTask = nil
    pendingCandidate = candidate
  }

  func peek() -> Target? {
    pendingTarget
  }

  func consumeIfAvailable(taskIDs: Set<String>, candidateIDs: Set<String>) -> Target? {
    guard let target = pendingTarget else { return nil }
    let isAvailable: Bool
    switch target {
    case .task(let id): isAvailable = taskIDs.contains(id)
    case .candidate(let id): isAvailable = candidateIDs.contains(id)
    }
    guard isAvailable else { return nil }
    clear()
    return target
  }

  private func clear() {
    pendingTarget = nil
    pendingTask = nil
    pendingCandidate = nil
  }
}

enum DashboardRecommendationDestination: Equatable {
  case suggested(candidateID: String)
  case task(taskID: String, workstreamID: String?)
  case thread(workstreamID: String, taskID: String?)
  case unavailable
}

struct DashboardRecommendation: Identifiable, Equatable {
  let id: String
  let interventionID: String
  let outputVersion: String
  let subjectKind: OmiAPI.RecommendationSubjectKind
  let subjectID: String
  let feedbackSubjectKind: OmiAPI.FeedbackSubjectKind
  let feedbackSubjectID: String
  let headline: String
  let whyNow: String
  let contextLabel: String?
  let recommendedAction: String
  let evidencePreview: String
  let evidenceCount: Int
  let dedupeKey: String
  let expiresAt: String
  let destination: DashboardRecommendationDestination
}

struct PendingDashboardFeedback: Codable {
  let request: OmiAPI.FeedbackCreate
  let idempotencyKey: String
  let accountGeneration: Int
}

protocol DashboardFeedbackOutboxPersisting: AnyObject {
  func currentOwnerID() -> String
  func load(ownerID: String) -> [PendingDashboardFeedback]
  func save(_ entries: [PendingDashboardFeedback], ownerID: String)
}

final class DashboardFeedbackOutboxDefaults: DashboardFeedbackOutboxPersisting {
  private let defaults: UserDefaults
  private let fixedOwnerID: String?

  init(defaults: UserDefaults = .standard, ownerID: String? = nil) {
    self.defaults = defaults
    fixedOwnerID = ownerID
  }

  func currentOwnerID() -> String {
    fixedOwnerID ?? defaults.string(forKey: .authUserId) ?? "signed-out"
  }

  private func key(ownerID: String) -> String { "whatMattersNowFeedbackOutbox.v1.\(ownerID)" }

  func load(ownerID: String) -> [PendingDashboardFeedback] {
    guard let data = defaults.data(forKey: key(ownerID: ownerID)) else { return [] }
    return (try? JSONDecoder().decode([PendingDashboardFeedback].self, from: data)) ?? []
  }

  func save(_ entries: [PendingDashboardFeedback], ownerID: String) {
    defaults.set(try? JSONEncoder().encode(entries), forKey: key(ownerID: ownerID))
  }
}

@MainActor
final class DashboardIntelligenceStore: ObservableObject {
  private struct OwnerScope: Equatable {
    let ownerID: String
    let revision: UInt
  }

  @Published private(set) var recommendations: [DashboardRecommendation] = []
  @Published private(set) var goals: [OmiAPI.GoalResponse] = []
  @Published private(set) var selectedGoalDetail: OmiAPI.GoalDetailProjection?
  @Published private(set) var isLoading = false
  @Published private(set) var accountGeneration: Int?
  @Published private(set) var focusReplacementGoalID: String?
  @Published var error: String?

  private let client: any DashboardIntelligenceClient
  private let outboxStore: any DashboardFeedbackOutboxPersisting
  private let now: () -> Date
  private let deviceID: () -> String?
  private let reportAttribution: (TaskIntelligenceAttributionEvent) -> Void
  private var activeOwnerID: String
  private var ownerRevision: UInt = 0
  private var activeLoadToken: UUID?
  private var loadingOwnerID: String?
  /// The in-flight same-owner load, so a concurrent `load()` (e.g. from
  /// `openRecommendation`) can await the real fetch instead of returning a no-op
  /// and then acting on a still-empty `recommendations`.
  private var activeLoadTask: Task<Void, Never>?
  private var activeLoadTaskID: UUID?
  private var pendingFeedback: [PendingDashboardFeedback]
  private var presentedInterventionIDs = Set<String>()
  private var didRegisterAutomationActions = false
  private var recommendationActionHandler: ((DashboardRecommendation) async -> Bool)?

  init(
    client: any DashboardIntelligenceClient = APIClient.shared,
    outboxStore: any DashboardFeedbackOutboxPersisting = DashboardFeedbackOutboxDefaults(),
    now: @escaping () -> Date = Date.init,
    deviceIDProvider: (() -> String?)? = nil,
    reportAttribution: ((TaskIntelligenceAttributionEvent) -> Void)? = nil
  ) {
    self.client = client
    self.outboxStore = outboxStore
    self.now = now
    self.deviceID = deviceIDProvider ?? { ClientDeviceService.shared.clientDeviceId }
    self.reportAttribution =
      reportAttribution ?? { AnalyticsManager.shared.taskIntelligenceAttribution($0) }
    let ownerID = outboxStore.currentOwnerID()
    activeOwnerID = ownerID
    self.pendingFeedback = outboxStore.load(ownerID: ownerID)
  }

  var focusedGoals: [OmiAPI.GoalResponse] {
    goals.filter { $0.status == .focused }
      .sorted { ($0.focusRank ?? Int.max, $0.updatedAt) < ($1.focusRank ?? Int.max, $1.updatedAt) }
  }

  var currentGoals: [OmiAPI.GoalResponse] {
    goals.filter { $0.status != .achieved && $0.status != .abandoned }
  }

  var endedGoals: [OmiAPI.GoalResponse] {
    goals.filter { $0.status == .achieved || $0.status == .abandoned }
  }

  func load() async {
    let ownerScope = captureOwnerScope()
    if loadingOwnerID == ownerScope.ownerID {
      // A same-owner load is already running. Await it rather than returning a
      // no-op, so callers that depend on the fetched data see the populated
      // result instead of a stale/empty one.
      if let activeLoadTask { await activeLoadTask.value }
      return
    }
    // Claim the dedup slot SYNCHRONOUSLY here — before spawning the task and
    // before the first await. performLoad() runs inside the Task (asynchronously),
    // so if we relied on it to set loadingOwnerID, a re-entrant same-owner load()
    // could run on the MainActor first, still see nil, and start a second
    // concurrent load (overwriting activeLoadTask) — defeating the dedup.
    loadingOwnerID = ownerScope.ownerID
    let taskID = UUID()
    let task = Task { [weak self] in
      guard let self else { return }
      await self.performLoad(ownerScope: ownerScope)
    }
    activeLoadTask = task
    activeLoadTaskID = taskID
    await task.value
    if activeLoadTaskID == taskID {
      activeLoadTask = nil
      activeLoadTaskID = nil
    }
  }

  private func performLoad(ownerScope: OwnerScope) async {
    let loadToken = UUID()
    activeLoadToken = loadToken
    loadingOwnerID = ownerScope.ownerID
    isLoading = true
    defer {
      if activeLoadToken == loadToken {
        activeLoadToken = nil
        loadingOwnerID = nil
        isLoading = false
      }
    }
    error = nil

    let control: OmiAPI.TaskWorkflowControl
    do {
      control = try await client.getCandidateWorkflowControl()
    } catch {
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      accountGeneration = nil
      recommendations = []
      goals = []
      self.error = UserFacingErrorPresentation.message(for: error, while: .dashboard)
      logError("Dashboard: Failed to load workflow control", error: error)
      return
    }
    guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }

    guard control.workflowMode == .read else {
      accountGeneration = nil
      recommendations = []
      goals = []
      return
    }
    accountGeneration = control.accountGeneration
    pendingFeedback = outboxStore.load(ownerID: ownerScope.ownerID)
    pendingFeedback.removeAll { $0.accountGeneration != control.accountGeneration }
    outboxStore.save(pendingFeedback, ownerID: ownerScope.ownerID)
    await retryPendingFeedback(ownerScope: ownerScope, loadToken: loadToken)
    guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
    do {
      let projection = try await client.getWhatMattersNow(deviceID: deviceID())
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      recommendations = projectForCurrentOwner(projection)
      emitPresentedInterventions(recommendations)
    } catch APIError.httpError(let statusCode, _) where statusCode == 404 {
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      // Canonical-read users outside the intelligence cohort retain calm
      // dashboard behavior while canonical Goals remain available.
      recommendations = []
    } catch {
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      recommendations = []
      self.error = UserFacingErrorPresentation.message(for: error, while: .dashboard)
      logError("Dashboard: What Matters Now projection unavailable", error: error)
    }
    do {
      let loadedGoals = try await client.getCanonicalGoals(includeEnded: true)
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      goals = loadedGoals
    } catch {
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      goals = []
      self.error = UserFacingErrorPresentation.message(for: error, while: .dashboard)
      logError("Dashboard: Failed to load canonical goals", error: error)
      return
    }
    if error == nil, !pendingFeedback.isEmpty {
      error = "Saved feedback will retry automatically."
    }
  }

  /// Apply a context-triggered canonical projection without coupling dashboard
  /// eligibility to notification settings or interruption policy.
  func applyContextProjection(_ projection: OmiAPI.WhatMattersNowProjection) {
    guard persistenceOwnerIsCurrent else {
      refreshOwnerScopedState()
      return
    }
    recommendations = projectForCurrentOwner(projection)
    emitPresentedInterventions(recommendations)
    error = nil
  }

  @discardableResult
  func openRecommendation(id: String) async -> Bool {
    let ownerScope = captureOwnerScope()
    if !recommendations.contains(where: { $0.id == id }) {
      await load()
      guard requireCurrentOwner(ownerScope) else { return false }
    }
    guard let recommendation = recommendations.first(where: { $0.id == id }),
      let recommendationActionHandler
    else {
      guard requireCurrentOwner(ownerScope) else { return false }
      error = "This review target is no longer available."
      return false
    }
    let opened = await recommendationActionHandler(recommendation)
    guard requireCurrentOwner(ownerScope) else { return false }
    if opened {
      TaskContextSubjectMatcher.shared.bindRecentContext(
        to: TaskContextSubject(
          kind: recommendation.subjectKind,
          id: recommendation.subjectID,
          workstreamID: Self.destinationWorkstreamID(recommendation.destination)
        ))
      await recordPrimaryAction(recommendation)
      guard requireCurrentOwner(ownerScope) else { return false }
    }
    return opened
  }

  func loadGoalDetail(goalID: String) async {
    let ownerScope = captureOwnerScope()
    do {
      let detail = try await client.getCanonicalGoalDetail(goalID: goalID)
      guard requireCurrentOwner(ownerScope) else { return }
      selectedGoalDetail = detail
      error = nil
    } catch {
      guard requireCurrentOwner(ownerScope) else { return }
      selectedGoalDetail = nil
      self.error = "Goal details could not be loaded."
    }
  }

  func candidateForNavigation(candidateID: String) async -> OmiAPI.CandidateRecord? {
    let ownerScope = captureOwnerScope()
    do {
      let candidate = try await client.getCanonicalCandidate(candidateID: candidateID)
      guard requireCurrentOwner(ownerScope) else { return nil }
      guard candidate.candidateId == candidateID,
        SuggestedTasksStore.canPresentForNavigation(candidate)
      else {
        error = "This Suggested item is no longer available."
        return nil
      }
      return candidate
    } catch {
      guard requireCurrentOwner(ownerScope) else { return nil }
      self.error = "This Suggested item could not be opened."
      return nil
    }
  }

  func taskForNavigation(taskID: String) async -> TaskActionItem? {
    let ownerScope = captureOwnerScope()
    do {
      let task = try await client.getActionItem(id: taskID)
      guard requireCurrentOwner(ownerScope) else { return nil }
      guard task.id == taskID else {
        error = "This task is no longer available."
        return nil
      }
      return task
    } catch {
      guard requireCurrentOwner(ownerScope) else { return nil }
      self.error = "This task could not be opened."
      return nil
    }
  }

  func clearGoalDetail() {
    guard persistenceOwnerIsCurrent else {
      refreshOwnerScopedState()
      return
    }
    selectedGoalDetail = nil
  }

  func createGoal(
    title: String,
    desiredOutcome: String,
    whyItMatters: String?,
    successCriteria: [String],
    idempotencyKey: String
  ) async -> Bool {
    let ownerScope = captureOwnerScope()
    guard let generation = accountGeneration else { return false }
    do {
      _ = try await client.createCanonicalGoal(
        title: title,
        desiredOutcome: desiredOutcome,
        whyItMatters: whyItMatters,
        successCriteria: successCriteria,
        accountGeneration: generation,
        idempotencyKey: idempotencyKey
      )
      guard requireCurrentOwner(ownerScope) else { return false }
      await load()
      guard requireCurrentOwner(ownerScope) else { return false }
      return true
    } catch {
      guard requireCurrentOwner(ownerScope) else { return false }
      self.error = "Goal could not be created."
      return false
    }
  }

  func recordPrimaryAction(_ recommendation: DashboardRecommendation) async {
    let ownerScope = captureOwnerScope()
    guard recommendations.contains(recommendation) else { return }
    _ = await recordFeedback(
      recommendation,
      action: .do_now,
      reason: nil,
      laterUntil: nil,
      idempotencyKey: "wmn:\(recommendation.interventionID):do-now",
      ownerScope: ownerScope
    )
    guard requireCurrentOwner(ownerScope) else { return }
    recommendations.removeAll { $0.id == recommendation.id }
  }

  func later(_ recommendation: DashboardRecommendation) async {
    let ownerScope = captureOwnerScope()
    guard recommendations.contains(recommendation) else { return }
    let until = now().addingTimeInterval(24 * 60 * 60)
    _ = await recordFeedback(
      recommendation,
      action: .later,
      reason: nil,
      laterUntil: Self.iso8601(until),
      idempotencyKey:
        "wmn:\(recommendation.interventionID):later:\(UUID().uuidString.lowercased())",
      ownerScope: ownerScope
    )
    guard requireCurrentOwner(ownerScope) else { return }
    recommendations.removeAll { $0.id == recommendation.id }
  }

  func dismiss(
    _ recommendation: DashboardRecommendation,
    reason: OmiAPI.TaskIntelligenceFeedbackReason?
  ) async {
    let ownerScope = captureOwnerScope()
    guard recommendations.contains(recommendation) else { return }
    _ = await recordFeedback(
      recommendation,
      action: .dismiss,
      reason: reason,
      laterUntil: nil,
      idempotencyKey: "wmn:\(recommendation.interventionID):dismiss:\(reason?.rawValue ?? "none")",
      ownerScope: ownerScope
    )
    guard requireCurrentOwner(ownerScope) else { return }
    recommendations.removeAll { $0.id == recommendation.id }
  }

  func focus(goalID: String, replacing replacementGoalID: String?) async -> Bool {
    let ownerScope = captureOwnerScope()
    guard let generation = accountGeneration else { return false }
    do {
      _ = try await client.focusCanonicalGoal(
        goalID: goalID,
        replacementGoalID: replacementGoalID,
        focusRank: nil,
        accountGeneration: generation,
        idempotencyKey: "goal-focus:\(goalID):\(UUID().uuidString.lowercased())"
      )
      guard requireCurrentOwner(ownerScope) else { return false }
      focusReplacementGoalID = nil
      await load()
      guard requireCurrentOwner(ownerScope) else { return false }
      return true
    } catch APIError.httpError(let statusCode, _)
      where statusCode == 409 && replacementGoalID == nil
    {
      guard requireCurrentOwner(ownerScope) else { return false }
      focusReplacementGoalID = goalID
      self.error = "Choose a focused goal to replace."
      return false
    } catch {
      guard requireCurrentOwner(ownerScope) else { return false }
      focusReplacementGoalID = nil
      self.error = "Goal focus could not be updated."
      return false
    }
  }

  func unfocus(goalID: String) async {
    let ownerScope = captureOwnerScope()
    guard let generation = accountGeneration else { return }
    do {
      _ = try await client.unfocusCanonicalGoal(
        goalID: goalID,
        accountGeneration: generation,
        idempotencyKey: "goal-unfocus:\(goalID):\(UUID().uuidString.lowercased())"
      )
      guard requireCurrentOwner(ownerScope) else { return }
      await load()
      guard requireCurrentOwner(ownerScope) else { return }
    } catch {
      guard requireCurrentOwner(ownerScope) else { return }
      self.error = "Goal focus could not be updated."
    }
  }

  func transition(goalID: String, status: OmiAPI.GoalStatus) async {
    let ownerScope = captureOwnerScope()
    guard let generation = accountGeneration else { return }
    do {
      _ = try await client.transitionCanonicalGoal(
        goalID: goalID,
        status: status,
        relationshipDisposition: "retain",
        accountGeneration: generation,
        idempotencyKey:
          "goal-lifecycle:\(goalID):\(status.rawValue):\(UUID().uuidString.lowercased())"
      )
      guard requireCurrentOwner(ownerScope) else { return }
      await load()
      guard requireCurrentOwner(ownerScope) else { return }
    } catch {
      guard requireCurrentOwner(ownerScope) else { return }
      self.error = "Goal lifecycle could not be updated."
    }
  }

  @discardableResult
  private func recordFeedback(
    _ recommendation: DashboardRecommendation,
    action: OmiAPI.TaskIntelligenceFeedbackAction,
    reason: OmiAPI.TaskIntelligenceFeedbackReason?,
    laterUntil: String?,
    idempotencyKey: String,
    ownerScope: OwnerScope
  ) async -> OmiAPI.FeedbackRecord? {
    guard requireCurrentOwner(ownerScope), let generation = accountGeneration else { return nil }
    let request = OmiAPI.FeedbackCreate(
      action: action,
      contextSnapshotHash: nil,
      interventionId: recommendation.interventionID,
      laterUntil: laterUntil,
      reason: reason,
      subjectId: recommendation.feedbackSubjectID,
      subjectKind: recommendation.feedbackSubjectKind
    )
    let entry = PendingDashboardFeedback(
      request: request,
      idempotencyKey: idempotencyKey,
      accountGeneration: generation
    )
    var ownerFeedback = outboxStore.load(ownerID: ownerScope.ownerID)
    ownerFeedback.removeAll { $0.idempotencyKey == idempotencyKey }
    ownerFeedback.append(entry)
    outboxStore.save(ownerFeedback, ownerID: ownerScope.ownerID)
    guard requireCurrentOwner(ownerScope) else { return nil }
    pendingFeedback = ownerFeedback
    do {
      let feedback = try await client.recordTaskFeedback(
        request, idempotencyKey: idempotencyKey, accountGeneration: generation)
      guard requireCurrentOwner(ownerScope) else { return nil }
      ownerFeedback = outboxStore.load(ownerID: ownerScope.ownerID)
      ownerFeedback.removeAll { $0.idempotencyKey == idempotencyKey }
      outboxStore.save(ownerFeedback, ownerID: ownerScope.ownerID)
      pendingFeedback = ownerFeedback
      error = nil
      reportAttribution(
        .feedbackRecorded(
          interventionID: recommendation.interventionID,
          surface: .whatMattersNow,
          action: action.rawValue,
          reason: reason?.rawValue,
          subjectKind: recommendation.feedbackSubjectKind.rawValue,
          subjectID: recommendation.feedbackSubjectID,
          candidateID: recommendation.subjectKind == .candidate ? recommendation.subjectID : nil,
          attributionChainID: feedback.attributionChainId
        ))
      return feedback
    } catch {
      guard requireCurrentOwner(ownerScope) else { return nil }
      self.error = "Saved. Feedback will retry automatically."
      return nil
    }
  }

  private func emitPresentedInterventions(_ recommendations: [DashboardRecommendation]) {
    for recommendation in recommendations {
      guard presentedInterventionIDs.insert(recommendation.interventionID).inserted else {
        continue
      }
      reportAttribution(
        .interventionPresented(
          interventionID: recommendation.interventionID,
          surface: .whatMattersNow,
          subjectKind: recommendation.subjectKind.rawValue,
          subjectID: recommendation.subjectID,
          candidateID: recommendation.subjectKind == .candidate ? recommendation.subjectID : nil
        ))
    }
  }

  private func retryPendingFeedback(ownerScope: OwnerScope, loadToken: UUID) async {
    var succeeded = Set<String>()
    for entry in outboxStore.load(ownerID: ownerScope.ownerID) {
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      do {
        _ = try await client.recordTaskFeedback(
          entry.request, idempotencyKey: entry.idempotencyKey,
          accountGeneration: entry.accountGeneration)
        guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
        succeeded.insert(entry.idempotencyKey)
      } catch {
        guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
        continue
      }
    }
    guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
    let remaining = outboxStore.load(ownerID: ownerScope.ownerID).filter {
      !succeeded.contains($0.idempotencyKey)
    }
    outboxStore.save(remaining, ownerID: ownerScope.ownerID)
    pendingFeedback = remaining
  }

  private var persistenceOwnerIsCurrent: Bool {
    activeOwnerID == outboxStore.currentOwnerID()
  }

  private func captureOwnerScope() -> OwnerScope {
    refreshOwnerScopedState()
    return OwnerScope(ownerID: activeOwnerID, revision: ownerRevision)
  }

  @discardableResult
  private func requireCurrentOwner(_ ownerScope: OwnerScope) -> Bool {
    guard ownerScopeIsCurrent(ownerScope) else {
      refreshOwnerScopedState()
      return false
    }
    return true
  }

  private func ownerScopeIsCurrent(_ ownerScope: OwnerScope) -> Bool {
    ownerScope.ownerID == activeOwnerID
      && ownerScope.revision == ownerRevision
      && outboxStore.currentOwnerID() == ownerScope.ownerID
  }

  private func loadScopeIsCurrent(_ ownerScope: OwnerScope, token: UUID) -> Bool {
    guard activeLoadToken == token, ownerScopeIsCurrent(ownerScope) else {
      refreshOwnerScopedState()
      return false
    }
    return true
  }

  @discardableResult
  private func refreshOwnerScopedState() -> Bool {
    let ownerID = outboxStore.currentOwnerID()
    guard ownerID != activeOwnerID else { return false }

    activeOwnerID = ownerID
    ownerRevision &+= 1
    activeLoadToken = nil
    loadingOwnerID = nil
    pendingFeedback = outboxStore.load(ownerID: ownerID)
    recommendations = []
    goals = []
    selectedGoalDetail = nil
    isLoading = false
    accountGeneration = nil
    focusReplacementGoalID = nil
    presentedInterventionIDs = []
    error = nil
    return true
  }

  private func projectForCurrentOwner(
    _ projection: OmiAPI.WhatMattersNowProjection
  ) -> [DashboardRecommendation] {
    Self.project(projection, now: now(), pendingFeedback: pendingFeedback)
  }

  static func project(
    _ projection: OmiAPI.WhatMattersNowProjection,
    now: Date
  ) -> [DashboardRecommendation] {
    project(projection, now: now, pendingFeedback: [])
  }

  private static func project(
    _ projection: OmiAPI.WhatMattersNowProjection,
    now: Date,
    pendingFeedback: [PendingDashboardFeedback]
  ) -> [DashboardRecommendation] {
    guard let projectionExpiry = parseDate(projection.expiresAt), projectionExpiry > now else {
      return []
    }
    var seenDedupeKeys = Set<String>()
    let recommendations = projection.recommendations.compactMap {
      item -> DashboardRecommendation? in
      let suppressedByPendingFeedback = pendingFeedback.contains { entry in
        guard entry.request.action == .later || entry.request.action == .dismiss else {
          return false
        }
        let matchesIntervention = entry.request.interventionId == item.interventionId
        let matchesSubject =
          entry.request.subjectKind == item.feedbackSubjectKind
          && entry.request.subjectId == item.feedbackSubjectId
        return matchesIntervention || matchesSubject
      }
      guard !suppressedByPendingFeedback else { return nil }
      guard let expiry = parseDate(item.expiresAt), expiry > now else { return nil }
      guard seenDedupeKeys.insert(item.dedupeKey).inserted else { return nil }
      let destination: DashboardRecommendationDestination
      switch item.subjectKind {
      case .candidate:
        destination = .suggested(candidateID: item.subjectId)
      case .task:
        destination = .task(
          taskID: item.destinationTaskId ?? item.subjectId,
          workstreamID: item.destinationWorkstreamId
        )
      case .workstream:
        destination = .thread(
          workstreamID: item.destinationWorkstreamId ?? item.subjectId,
          taskID: item.destinationTaskId
        )
      case .artifact, .decision, .agent_open_loop:
        guard let workstreamID = item.destinationWorkstreamId else { return nil }
        destination = .thread(workstreamID: workstreamID, taskID: item.destinationTaskId)
      case ._unknown:
        return nil
      }
      return DashboardRecommendation(
        id: "\(item.outputVersion):\(item.dedupeKey)",
        interventionID: item.interventionId,
        outputVersion: item.outputVersion,
        subjectKind: item.subjectKind,
        subjectID: item.subjectId,
        feedbackSubjectKind: item.feedbackSubjectKind,
        feedbackSubjectID: item.feedbackSubjectId,
        headline: item.headline,
        whyNow: item.whyNow,
        contextLabel: item.goalOrWorkstreamLabel,
        recommendedAction: item.recommendedAction,
        evidencePreview: item.evidencePreview,
        evidenceCount: item.evidenceRefs.count,
        dedupeKey: item.dedupeKey,
        expiresAt: item.expiresAt,
        destination: destination
      )
    }
    return Array(recommendations.prefix(3))
  }

  private static func parseDate(_ value: String) -> Date? {
    let precise = ISO8601DateFormatter()
    precise.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return precise.date(from: value) ?? ISO8601DateFormatter().date(from: value)
  }

  private static func iso8601(_ value: Date) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: value)
  }

  func registerAutomationActions() {
    guard DesktopAutomationLaunchOptions.isEnabled, !didRegisterAutomationActions else { return }
    didRegisterAutomationActions = true
    DesktopAutomationActionRegistry.shared.register(
      name: "refresh_what_matters_now",
      summary: "Refresh canonical recommendations and goals",
      params: []
    ) { [weak self] _ in
      guard let self else { return ["error": "dashboard intelligence store deallocated"] }
      await self.load()
      return [
        "recommendations": String(self.recommendations.count),
        "focused_goals": String(self.focusedGoals.count),
        "output_ids": self.recommendations.map(\.id).joined(separator: ","),
        "subjects": self.recommendations.map(Self.automationSummary).joined(separator: ","),
        "error": self.error ?? "",
      ]
    }
    DesktopAutomationActionRegistry.shared.register(
      name: "open_what_matters_now",
      summary: "Open one canonical recommendation by stable output id",
      params: ["recommendation_id"]
    ) { [weak self] params in
      guard let self else { return ["error": "dashboard intelligence store deallocated"] }
      guard let recommendationID = params["recommendation_id"], !recommendationID.isEmpty else {
        return ["error": "recommendation_id is required"]
      }
      if !self.recommendations.contains(where: { $0.id == recommendationID }) { await self.load() }
      let recommendation = self.recommendations.first(where: { $0.id == recommendationID })
      let opened = await self.openRecommendation(id: recommendationID)
      return [
        "success": opened ? "true" : "false",
        "subject_kind": recommendation?.subjectKind.rawValue ?? "",
        "subject_id": recommendation?.subjectID ?? "",
        "destination": recommendation.map {
          Self.automationDestination($0.destination)
        } ?? "",
        "error": self.error ?? "",
      ]
    }
    DesktopAutomationActionRegistry.shared.register(
      name: "focus_goal",
      summary: "Focus a canonical goal with optional explicit replacement",
      params: ["goal_id", "replacement_goal_id"]
    ) { [weak self] params in
      guard let self else { return ["error": "dashboard intelligence store deallocated"] }
      guard let goalID = params["goal_id"], !goalID.isEmpty else {
        return ["error": "goal_id is required"]
      }
      let success = await self.focus(goalID: goalID, replacing: params["replacement_goal_id"])
      return ["success": success ? "true" : "false", "error": self.error ?? ""]
    }
  }

  func setRecommendationActionHandler(_ handler: ((DashboardRecommendation) async -> Bool)?) {
    recommendationActionHandler = handler
  }

  private static func automationSummary(_ recommendation: DashboardRecommendation) -> String {
    [
      recommendation.id,
      recommendation.subjectKind.rawValue,
      recommendation.subjectID,
      automationDestination(recommendation.destination),
    ].joined(separator: "|")
  }

  private static func automationDestination(_ destination: DashboardRecommendationDestination)
    -> String
  {
    switch destination {
    case .suggested(let candidateID): return "candidate:\(candidateID)"
    case .task(let taskID, let workstreamID): return "task:\(taskID):\(workstreamID ?? "")"
    case .thread(let workstreamID, let taskID): return "thread:\(workstreamID):\(taskID ?? "")"
    case .unavailable: return "unavailable"
    }
  }

  private static func destinationWorkstreamID(_ destination: DashboardRecommendationDestination)
    -> String?
  {
    switch destination {
    case .task(_, let workstreamID): return workstreamID
    case .thread(let workstreamID, _): return workstreamID
    case .suggested, .unavailable: return nil
    }
  }
}
