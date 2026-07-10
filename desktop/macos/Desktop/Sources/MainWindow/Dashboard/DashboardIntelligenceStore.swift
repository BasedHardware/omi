import Foundation

protocol DashboardIntelligenceClient: AnyObject {
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

extension APIClient: DashboardIntelligenceClient {}

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
  func load() -> [PendingDashboardFeedback]
  func save(_ entries: [PendingDashboardFeedback])
}

final class DashboardFeedbackOutboxDefaults: DashboardFeedbackOutboxPersisting {
  private let defaults: UserDefaults
  private let key: String

  init(defaults: UserDefaults = .standard, ownerID: String? = nil) {
    self.defaults = defaults
    let owner = ownerID ?? defaults.string(forKey: "auth_userId") ?? "signed-out"
    self.key = "whatMattersNowFeedbackOutbox.v1.\(owner)"
  }

  func load() -> [PendingDashboardFeedback] {
    guard let data = defaults.data(forKey: key) else { return [] }
    return (try? JSONDecoder().decode([PendingDashboardFeedback].self, from: data)) ?? []
  }

  func save(_ entries: [PendingDashboardFeedback]) {
    defaults.set(try? JSONEncoder().encode(entries), forKey: key)
  }
}

@MainActor
final class DashboardIntelligenceStore: ObservableObject {
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
  private var pendingFeedback: [PendingDashboardFeedback]
  private var didRegisterAutomationActions = false
  private var recommendationActionHandler: ((DashboardRecommendation) async -> Bool)?

  init(
    client: any DashboardIntelligenceClient = APIClient.shared,
    outboxStore: any DashboardFeedbackOutboxPersisting = DashboardFeedbackOutboxDefaults(),
    now: @escaping () -> Date = Date.init
  ) {
    self.client = client
    self.outboxStore = outboxStore
    self.now = now
    self.pendingFeedback = outboxStore.load()
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
    guard !isLoading else { return }
    isLoading = true
    defer { isLoading = false }
    do {
      let control = try await client.getCandidateWorkflowControl()
      guard control.workflowMode == .read else {
        accountGeneration = nil
        recommendations = []
        goals = []
        return
      }
      accountGeneration = control.accountGeneration
      pendingFeedback.removeAll { $0.accountGeneration != control.accountGeneration }
      outboxStore.save(pendingFeedback)
      await retryPendingFeedback()
      do {
        let projection = try await client.getWhatMattersNow(deviceID: nil)
        recommendations = Self.project(projection, now: now())
      } catch {
        // Canonical-read users outside the intelligence cohort retain calm
        // dashboard behavior while canonical Goals remain available.
        recommendations = []
      }
      goals = try await client.getCanonicalGoals(includeEnded: true)
      error = pendingFeedback.isEmpty ? nil : "Saved feedback will retry automatically."
    } catch {
      recommendations = []
      self.error = "What matters now could not be refreshed."
    }
  }

  func loadGoalDetail(goalID: String) async {
    do {
      selectedGoalDetail = try await client.getCanonicalGoalDetail(goalID: goalID)
      error = nil
    } catch {
      selectedGoalDetail = nil
      self.error = "Goal details could not be loaded."
    }
  }

  func candidateForNavigation(candidateID: String) async -> OmiAPI.CandidateRecord? {
    do {
      let candidate = try await client.getCanonicalCandidate(candidateID: candidateID)
      guard candidate.candidateId == candidateID,
        SuggestedTasksStore.canPresentForNavigation(candidate)
      else {
        error = "This Suggested item is no longer available."
        return nil
      }
      return candidate
    } catch {
      self.error = "This Suggested item could not be opened."
      return nil
    }
  }

  func taskForNavigation(taskID: String) async -> TaskActionItem? {
    do {
      let task = try await client.getActionItem(id: taskID)
      guard task.id == taskID else {
        error = "This task is no longer available."
        return nil
      }
      return task
    } catch {
      self.error = "This task could not be opened."
      return nil
    }
  }

  func clearGoalDetail() {
    selectedGoalDetail = nil
  }

  func createGoal(
    title: String,
    desiredOutcome: String,
    whyItMatters: String?,
    successCriteria: [String],
    idempotencyKey: String
  ) async -> Bool {
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
      await load()
      return true
    } catch {
      self.error = "Goal could not be created."
      return false
    }
  }

  func recordPrimaryAction(_ recommendation: DashboardRecommendation) async {
    await recordFeedback(
      recommendation,
      action: .do_now,
      reason: nil,
      laterUntil: nil,
      idempotencyKey: "wmn:\(recommendation.interventionID):do-now"
    )
    recommendations.removeAll { $0.id == recommendation.id }
  }

  func later(_ recommendation: DashboardRecommendation) async {
    let until = now().addingTimeInterval(24 * 60 * 60)
    await recordFeedback(
      recommendation,
      action: .later,
      reason: nil,
      laterUntil: Self.iso8601(until),
      idempotencyKey: "wmn:\(recommendation.interventionID):later:\(UUID().uuidString.lowercased())"
    )
    recommendations.removeAll { $0.id == recommendation.id }
  }

  func dismiss(
    _ recommendation: DashboardRecommendation,
    reason: OmiAPI.TaskIntelligenceFeedbackReason?
  ) async {
    await recordFeedback(
      recommendation,
      action: .dismiss,
      reason: reason,
      laterUntil: nil,
      idempotencyKey: "wmn:\(recommendation.interventionID):dismiss:\(reason?.rawValue ?? "none")"
    )
    recommendations.removeAll { $0.id == recommendation.id }
  }

  func focus(goalID: String, replacing replacementGoalID: String?) async -> Bool {
    guard let generation = accountGeneration else { return false }
    do {
      _ = try await client.focusCanonicalGoal(
        goalID: goalID,
        replacementGoalID: replacementGoalID,
        focusRank: nil,
        accountGeneration: generation,
        idempotencyKey: "goal-focus:\(goalID):\(UUID().uuidString.lowercased())"
      )
      focusReplacementGoalID = nil
      await load()
      return true
    } catch APIError.httpError(let statusCode, _) where statusCode == 409 && replacementGoalID == nil {
      focusReplacementGoalID = goalID
      self.error = "Choose a focused goal to replace."
      return false
    } catch {
      focusReplacementGoalID = nil
      self.error = "Goal focus could not be updated."
      return false
    }
  }

  func unfocus(goalID: String) async {
    guard let generation = accountGeneration else { return }
    do {
      _ = try await client.unfocusCanonicalGoal(
        goalID: goalID,
        accountGeneration: generation,
        idempotencyKey: "goal-unfocus:\(goalID):\(UUID().uuidString.lowercased())"
      )
      await load()
    } catch {
      self.error = "Goal focus could not be updated."
    }
  }

  func transition(goalID: String, status: OmiAPI.GoalStatus) async {
    guard let generation = accountGeneration else { return }
    do {
      _ = try await client.transitionCanonicalGoal(
        goalID: goalID,
        status: status,
        relationshipDisposition: "retain",
        accountGeneration: generation,
        idempotencyKey: "goal-lifecycle:\(goalID):\(status.rawValue):\(UUID().uuidString.lowercased())"
      )
      await load()
    } catch {
      self.error = "Goal lifecycle could not be updated."
    }
  }

  private func recordFeedback(
    _ recommendation: DashboardRecommendation,
    action: OmiAPI.TaskIntelligenceFeedbackAction,
    reason: OmiAPI.TaskIntelligenceFeedbackReason?,
    laterUntil: String?,
    idempotencyKey: String
  ) async {
    guard let generation = accountGeneration else { return }
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
    pendingFeedback.removeAll { $0.idempotencyKey == idempotencyKey }
    pendingFeedback.append(entry)
    outboxStore.save(pendingFeedback)
    do {
      _ = try await client.recordTaskFeedback(
        request, idempotencyKey: idempotencyKey, accountGeneration: generation)
      pendingFeedback.removeAll { $0.idempotencyKey == idempotencyKey }
      outboxStore.save(pendingFeedback)
      error = nil
    } catch {
      self.error = "Saved. Feedback will retry automatically."
    }
  }

  private func retryPendingFeedback() async {
    var remaining: [PendingDashboardFeedback] = []
    for entry in pendingFeedback {
      do {
        _ = try await client.recordTaskFeedback(
          entry.request, idempotencyKey: entry.idempotencyKey, accountGeneration: entry.accountGeneration)
      } catch {
        remaining.append(entry)
      }
    }
    pendingFeedback = remaining
    outboxStore.save(remaining)
  }

  static func project(
    _ projection: OmiAPI.WhatMattersNowProjection,
    now: Date
  ) -> [DashboardRecommendation] {
    guard let projectionExpiry = parseDate(projection.expiresAt), projectionExpiry > now else { return [] }
    var seenDedupeKeys = Set<String>()
    let recommendations = projection.recommendations.compactMap { item -> DashboardRecommendation? in
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
        evidenceCount: item.evidenceRefs?.count ?? 0,
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
      guard let recommendation = self.recommendations.first(where: { $0.id == recommendationID }) else {
        return ["success": "false", "error": "recommendation not found"]
      }
      guard let handler = self.recommendationActionHandler else {
        return ["success": "false", "error": "dashboard recommendation router unavailable"]
      }
      let opened = await handler(recommendation)
      if opened { await self.recordPrimaryAction(recommendation) }
      return [
        "success": opened ? "true" : "false",
        "subject_kind": recommendation.subjectKind.rawValue,
        "subject_id": recommendation.subjectID,
        "destination": Self.automationDestination(recommendation.destination),
        "error": self.error ?? "",
      ]
    }
    DesktopAutomationActionRegistry.shared.register(
      name: "focus_goal",
      summary: "Focus a canonical goal with optional explicit replacement",
      params: ["goal_id", "replacement_goal_id"]
    ) { [weak self] params in
      guard let self else { return ["error": "dashboard intelligence store deallocated"] }
      guard let goalID = params["goal_id"], !goalID.isEmpty else { return ["error": "goal_id is required"] }
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

  private static func automationDestination(_ destination: DashboardRecommendationDestination) -> String {
    switch destination {
    case .suggested(let candidateID): return "candidate:\(candidateID)"
    case .task(let taskID, let workstreamID): return "task:\(taskID):\(workstreamID ?? "")"
    case .thread(let workstreamID, let taskID): return "thread:\(workstreamID):\(taskID ?? "")"
    case .unavailable: return "unavailable"
    }
  }
}
