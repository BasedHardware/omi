import CryptoKit
import Foundation
import OmiSupport

protocol SuggestedTasksClient: AnyObject, Sendable {
  func getCandidateWorkflowControl() async throws -> OmiAPI.TaskWorkflowControl
  func listCanonicalCandidates(status: String, limit: Int) async throws -> [OmiAPI.CandidateRecord]
  func registerTaskIntervention(
    _ request: OmiAPI.InterventionCreate, idempotencyKey: String, accountGeneration: Int
  ) async throws -> OmiAPI.InterventionRecord
  func recordTaskFeedback(
    _ request: OmiAPI.FeedbackCreate, idempotencyKey: String, accountGeneration: Int
  ) async throws -> OmiAPI.FeedbackRecord
  func createTaskOutcome(
    _ request: OmiAPI.OutcomeCreate, idempotencyKey: String, accountGeneration: Int
  ) async throws -> OmiAPI.OutcomeRecord
  func acceptCanonicalCandidate(
    candidateID: String, accountGeneration: Int
  ) async throws -> OmiAPI.CandidateResolutionReceipt
  func rejectCanonicalCandidate(
    candidateID: String, reason: String?, accountGeneration: Int
  ) async throws -> OmiAPI.CandidateResolutionReceipt
  func updateSuggestedTaskDescription(id: String, description: String) async throws
}

extension APIClient: SuggestedTasksClient {}

enum SuggestedCardAction: String, Equatable {
  case doNow
  case later
  case dismiss
  case saveEdit
  case cancelEdit
  case alreadyHandled
  case notMine
  case notUseful
}

enum SuggestedCardState: Equatable {
  case ready
  case editing
  case dismissReasons
  case busy
}

enum SuggestedActionPolicy {
  static func actions(for state: SuggestedCardState) -> [SuggestedCardAction] {
    switch state {
    case .ready: return [.doNow, .later, .dismiss]
    case .editing: return [.saveEdit, .cancelEdit]
    case .dismissReasons: return [.alreadyHandled, .notMine, .notUseful]
    case .busy: return []
    }
  }
}

struct SuggestedCandidate: Identifiable, Equatable {
  let id: String
  let title: String
  let detail: String?
  let provenanceLabel: String
  let evidenceCount: Int
  let accountGeneration: Int
  let isEditableTask: Bool
  let createdAt: String
}

protocol SuggestedSuppressionPersisting: AnyObject {
  func currentOwnerID() -> String
  func load(ownerID: String) -> [String: Date]
  func save(_ suppressions: [String: Date], ownerID: String)
}

final class SuggestedSuppressionDefaults: SuggestedSuppressionPersisting {
  private let defaults: UserDefaults
  private let fixedOwnerID: String?

  init(defaults: UserDefaults = .standard, ownerID: String? = nil) {
    self.defaults = defaults
    fixedOwnerID = ownerID
  }

  func currentOwnerID() -> String {
    fixedOwnerID ?? defaults.string(forKey: .authUserId) ?? "signed-out"
  }

  private func key(ownerID: String) -> String {
    "canonicalSuggestedCandidateSuppressions.v1.\(ownerID)"
  }

  func load(ownerID: String) -> [String: Date] {
    guard let raw = defaults.dictionary(forKey: key(ownerID: ownerID)) as? [String: Double] else {
      return [:]
    }
    return raw.mapValues(Date.init(timeIntervalSince1970:))
  }

  func save(_ suppressions: [String: Date], ownerID: String) {
    defaults.set(suppressions.mapValues(\.timeIntervalSince1970), forKey: key(ownerID: ownerID))
  }
}

struct PendingSuggestedFeedback: Codable {
  let request: OmiAPI.FeedbackCreate
  let idempotencyKey: String
  let accountGeneration: Int
  let interventionRequest: OmiAPI.InterventionCreate?
  let interventionIdempotencyKey: String?
}

protocol SuggestedFeedbackOutboxPersisting: AnyObject {
  func currentOwnerID() -> String
  func load(ownerID: String) -> [PendingSuggestedFeedback]
  func save(_ entries: [PendingSuggestedFeedback], ownerID: String)
}

final class SuggestedFeedbackOutboxDefaults: SuggestedFeedbackOutboxPersisting {
  private let defaults: UserDefaults
  private let fixedOwnerID: String?

  init(defaults: UserDefaults = .standard, ownerID: String? = nil) {
    self.defaults = defaults
    fixedOwnerID = ownerID
  }

  func currentOwnerID() -> String {
    fixedOwnerID ?? defaults.string(forKey: .authUserId) ?? "signed-out"
  }

  private func key(ownerID: String) -> String { "canonicalSuggestedFeedbackOutbox.v1.\(ownerID)" }

  func load(ownerID: String) -> [PendingSuggestedFeedback] {
    guard let data = defaults.data(forKey: key(ownerID: ownerID)) else { return [] }
    return (try? JSONDecoder().decode([PendingSuggestedFeedback].self, from: data)) ?? []
  }

  func save(_ entries: [PendingSuggestedFeedback], ownerID: String) {
    defaults.set(try? JSONEncoder().encode(entries), forKey: key(ownerID: ownerID))
  }
}

@MainActor
final class SuggestedTasksStore: ObservableObject {
  private struct OwnerScope: Equatable {
    let suppressionOwnerID: String
    let feedbackOwnerID: String
    let revision: UInt
  }

  private static let maxVisibleCandidates = 5

  @Published private(set) var candidates: [SuggestedCandidate] = []
  @Published private(set) var isLoading = false
  @Published private(set) var busyCandidateIDs: Set<String> = []
  @Published var error: String?

  private let client: any SuggestedTasksClient
  private let suppressionStore: any SuggestedSuppressionPersisting
  private let feedbackOutboxStore: any SuggestedFeedbackOutboxPersisting
  private let now: () -> Date
  private let reportAttribution: (TaskIntelligenceAttributionEvent) -> Void
  private var recordsByID: [String: OmiAPI.CandidateRecord] = [:]
  private var interventionIDs: [String: String] = [:]
  private var interventionAttributionChainIDs: [String: String] = [:]
  private var registeringInterventionIDs: Set<String> = []
  private var activeSuppressionOwnerID: String
  private var activeFeedbackOwnerID: String
  private var ownerRevision: UInt = 0
  private var activeLoadToken: UUID?
  private var loadingOwnerScope: OwnerScope?
  private var suppressions: [String: Date]
  private var pendingFeedback: [PendingSuggestedFeedback]
  private var didRegisterAutomationActions = false

  init(
    client: any SuggestedTasksClient = APIClient.shared,
    suppressionStore: any SuggestedSuppressionPersisting = SuggestedSuppressionDefaults(),
    feedbackOutboxStore: any SuggestedFeedbackOutboxPersisting = SuggestedFeedbackOutboxDefaults(),
    now: @escaping () -> Date = Date.init,
    reportAttribution: ((TaskIntelligenceAttributionEvent) -> Void)? = nil
  ) {
    self.client = client
    self.suppressionStore = suppressionStore
    self.feedbackOutboxStore = feedbackOutboxStore
    self.now = now
    self.reportAttribution =
      reportAttribution ?? { AnalyticsManager.shared.taskIntelligenceAttribution($0) }
    let suppressionOwnerID = suppressionStore.currentOwnerID()
    let feedbackOwnerID = feedbackOutboxStore.currentOwnerID()
    activeSuppressionOwnerID = suppressionOwnerID
    activeFeedbackOwnerID = feedbackOwnerID
    self.suppressions = suppressionStore.load(ownerID: suppressionOwnerID)
    self.pendingFeedback = feedbackOutboxStore.load(ownerID: feedbackOwnerID)
  }

  func load() async {
    let ownerScope = captureOwnerScope()
    guard loadingOwnerScope != ownerScope else { return }
    let loadToken = UUID()
    activeLoadToken = loadToken
    loadingOwnerScope = ownerScope
    isLoading = true
    defer {
      if activeLoadToken == loadToken {
        activeLoadToken = nil
        loadingOwnerScope = nil
        isLoading = false
      }
    }

    let control: OmiAPI.TaskWorkflowControl
    do {
      control = try await client.getCandidateWorkflowControl()
    } catch {
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      self.error = "Suggested items could not be refreshed."
      return
    }
    guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }

    guard control.workflowMode == .read else {
      candidates = []
      recordsByID = [:]
      return
    }
    pendingFeedback.removeAll { $0.accountGeneration != control.accountGeneration }
    feedbackOutboxStore.save(pendingFeedback, ownerID: ownerScope.feedbackOwnerID)
    await retryPendingFeedback(ownerScope: ownerScope, loadToken: loadToken)
    guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }

    let records: [OmiAPI.CandidateRecord]
    do {
      records = try await client.listCanonicalCandidates(status: "pending", limit: 100)
    } catch APIError.httpError(let statusCode, _) where statusCode == 404 {
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      candidates = []
      recordsByID = [:]
      error = nil
      return
    } catch {
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      self.error = "Suggested items could not be refreshed."
      return
    }
    guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }

    let pendingRecords = records.filter { $0.status == nil || $0.status == .pending }
    let checkedAt = now()
    suppressions = suppressions.filter { $0.value > checkedAt }
    suppressionStore.save(suppressions, ownerID: ownerScope.suppressionOwnerID)
    let visible =
      pendingRecords
      .filter { suppressions[$0.candidateId] == nil }
      .compactMap { record in Self.project(record).map { (record: record, candidate: $0) } }
      .prefix(Self.maxVisibleCandidates)
    recordsByID = Dictionary(lastWriteWins: visible.map { ($0.record.candidateId, $0.record) })
    candidates = visible.map(\.candidate)
    error = pendingFeedback.isEmpty ? nil : "Saved feedback attribution will retry automatically."
  }

  @discardableResult
  func revealCandidateForNavigation(_ record: OmiAPI.CandidateRecord) -> Bool {
    guard persistenceOwnersAreCurrent else {
      refreshOwnerScopedState()
      return false
    }
    guard let projected = Self.project(record) else { return false }
    recordsByID[record.candidateId] = record
    if !candidates.contains(where: { $0.id == record.candidateId }) {
      insertCandidateBounded(projected, at: 0)
    }
    return true
  }

  static func canPresentForNavigation(_ record: OmiAPI.CandidateRecord) -> Bool {
    project(record) != nil
  }

  func presented(candidateID: String) async {
    guard persistenceOwnersAreCurrent else {
      refreshOwnerScopedState()
      return
    }
    guard let record = recordsByID[candidateID],
      interventionIDs[candidateID] == nil,
      !registeringInterventionIDs.contains(candidateID)
    else { return }
    registeringInterventionIDs.insert(candidateID)
    defer { registeringInterventionIDs.remove(candidateID) }
    if let intervention = try? await ensureIntervention(for: record) {
      reportAttribution(
        .interventionPresented(
          interventionID: intervention.interventionId,
          surface: .suggested,
          subjectKind: OmiAPI.FeedbackSubjectKind.candidate.rawValue,
          subjectID: candidateID,
          candidateID: candidateID,
          attributionChainID: intervention.attributionChainId
        ))
    }
    guard persistenceOwnersAreCurrent else {
      refreshOwnerScopedState()
      return
    }
  }

  func doNow(candidateID: String, editedTitle: String?) async -> String? {
    guard persistenceOwnersAreCurrent,
      let record = recordsByID[candidateID], !busyCandidateIDs.contains(candidateID)
    else {
      refreshOwnerScopedState()
      return nil
    }
    let suppressionOwnerID = activeSuppressionOwnerID
    let feedbackOwnerID = activeFeedbackOwnerID
    let trimmed = editedTitle?.trimmingCharacters(in: .whitespacesAndNewlines)
    let originalTitle = Self.title(for: record)
    let changedTitle = trimmed.flatMap { $0.isEmpty || $0 == originalTitle ? nil : $0 }
    guard let removed = removeCandidate(candidateID) else { return nil }
    busyCandidateIDs.insert(candidateID)
    defer { busyCandidateIDs.remove(candidateID) }
    let receipt: OmiAPI.CandidateResolutionReceipt
    do {
      receipt = try await client.acceptCanonicalCandidate(
        candidateID: candidateID, accountGeneration: record.accountGeneration)
    } catch {
      guard
        ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
      else {
        refreshOwnerScopedState()
        return nil
      }
      restoreCandidate(removed)
      self.error = "That Suggested action did not sync. Try again."
      return nil
    }
    guard ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
    else {
      refreshOwnerScopedState()
      return nil
    }
    var feedbackAction = OmiAPI.TaskIntelligenceFeedbackAction.accept_candidate
    if let changedTitle, let taskID = receipt.taskId {
      do {
        try await client.updateSuggestedTaskDescription(id: taskID, description: changedTitle)
        guard
          ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
        else {
          refreshOwnerScopedState()
          return nil
        }
        feedbackAction = .edit
      } catch {
        guard
          ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
        else {
          refreshOwnerScopedState()
          return nil
        }
        self.error = "The task was kept, but the edit did not sync."
      }
    }
    let feedbackRequest = OmiAPI.FeedbackCreate(
      action: feedbackAction,
      contextSnapshotHash: nil,
      interventionId: nil,
      laterUntil: nil,
      reason: nil,
      subjectId: candidateID,
      subjectKind: .candidate
    )
    let feedbackRecord = await recordOrQueueFeedback(
      feedbackRequest,
      idempotencyKey: "suggested:\(candidateID):\(feedbackAction.rawValue)",
      record: record
    )
    guard ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
    else {
      refreshOwnerScopedState()
      return nil
    }
    if feedbackRecord != nil && feedbackAction == .accept_candidate && changedTitle == nil {
      error = nil
    }
    return receipt.taskId
  }

  func later(candidateID: String) async {
    guard persistenceOwnersAreCurrent,
      let record = recordsByID[candidateID], !busyCandidateIDs.contains(candidateID)
    else {
      refreshOwnerScopedState()
      return
    }
    let until = now().addingTimeInterval(24 * 60 * 60)
    guard removeCandidate(candidateID) != nil else { return }
    busyCandidateIDs.insert(candidateID)
    defer { busyCandidateIDs.remove(candidateID) }
    suppressions[candidateID] = until
    suppressionStore.save(suppressions, ownerID: activeSuppressionOwnerID)
    _ = await recordOrQueueFeedback(
      OmiAPI.FeedbackCreate(
        action: .later,
        contextSnapshotHash: nil,
        interventionId: nil,
        laterUntil: Self.iso8601(until),
        reason: nil,
        subjectId: candidateID,
        subjectKind: .candidate
      ),
      idempotencyKey: "suggested:\(candidateID):later:\(UUID().uuidString.lowercased())",
      record: record
    )
  }

  func dismiss(candidateID: String, reason: OmiAPI.TaskIntelligenceFeedbackReason?) async {
    guard persistenceOwnersAreCurrent,
      let record = recordsByID[candidateID], !busyCandidateIDs.contains(candidateID)
    else {
      refreshOwnerScopedState()
      return
    }
    let suppressionOwnerID = activeSuppressionOwnerID
    let feedbackOwnerID = activeFeedbackOwnerID
    let until = now().addingTimeInterval(30 * 24 * 60 * 60)
    guard let removed = removeCandidate(candidateID) else { return }
    busyCandidateIDs.insert(candidateID)
    defer { busyCandidateIDs.remove(candidateID) }
    do {
      _ = try await client.rejectCanonicalCandidate(
        candidateID: candidateID,
        reason: reason?.rawValue,
        accountGeneration: record.accountGeneration
      )
    } catch {
      guard
        ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
      else {
        refreshOwnerScopedState()
        return
      }
      restoreCandidate(removed)
      self.error = "That Suggested action did not sync. Try again."
      return
    }
    guard ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
    else {
      refreshOwnerScopedState()
      return
    }
    suppressions[candidateID] = until
    suppressionStore.save(suppressions, ownerID: activeSuppressionOwnerID)
    let feedbackRequest = OmiAPI.FeedbackCreate(
      action: .dismiss,
      contextSnapshotHash: nil,
      interventionId: nil,
      laterUntil: nil,
      reason: reason,
      subjectId: candidateID,
      subjectKind: .candidate
    )
    _ = await recordOrQueueFeedback(
      feedbackRequest,
      idempotencyKey: "suggested:\(candidateID):dismiss:\(reason?.rawValue ?? "none")",
      record: record
    )
  }

  private var persistenceOwnersAreCurrent: Bool {
    ownersAreCurrent(
      suppressionOwnerID: activeSuppressionOwnerID,
      feedbackOwnerID: activeFeedbackOwnerID
    )
  }

  private func captureOwnerScope() -> OwnerScope {
    refreshOwnerScopedState()
    return OwnerScope(
      suppressionOwnerID: activeSuppressionOwnerID,
      feedbackOwnerID: activeFeedbackOwnerID,
      revision: ownerRevision
    )
  }

  private func loadScopeIsCurrent(_ ownerScope: OwnerScope, token: UUID) -> Bool {
    guard activeLoadToken == token,
      ownerScope.revision == ownerRevision,
      ownersAreCurrent(
        suppressionOwnerID: ownerScope.suppressionOwnerID,
        feedbackOwnerID: ownerScope.feedbackOwnerID
      )
    else {
      refreshOwnerScopedState()
      return false
    }
    return true
  }

  private func ownersAreCurrent(suppressionOwnerID: String, feedbackOwnerID: String) -> Bool {
    activeSuppressionOwnerID == suppressionOwnerID
      && activeFeedbackOwnerID == feedbackOwnerID
      && suppressionStore.currentOwnerID() == suppressionOwnerID
      && feedbackOutboxStore.currentOwnerID() == feedbackOwnerID
  }

  @discardableResult
  private func refreshOwnerScopedState() -> Bool {
    let suppressionOwnerID = suppressionStore.currentOwnerID()
    let feedbackOwnerID = feedbackOutboxStore.currentOwnerID()
    let changed =
      suppressionOwnerID != activeSuppressionOwnerID || feedbackOwnerID != activeFeedbackOwnerID
    guard changed else { return false }

    activeSuppressionOwnerID = suppressionOwnerID
    activeFeedbackOwnerID = feedbackOwnerID
    ownerRevision &+= 1
    activeLoadToken = nil
    loadingOwnerScope = nil
    suppressions = suppressionStore.load(ownerID: suppressionOwnerID)
    pendingFeedback = feedbackOutboxStore.load(ownerID: feedbackOwnerID)
    candidates = []
    recordsByID = [:]
    interventionIDs = [:]
    interventionAttributionChainIDs = [:]
    registeringInterventionIDs = []
    busyCandidateIDs = []
    isLoading = false
    error = nil
    return true
  }

  private func removeCandidate(_ candidateID: String) -> (
    candidate: SuggestedCandidate, index: Int
  )? {
    guard let index = candidates.firstIndex(where: { $0.id == candidateID }) else { return nil }
    return (candidates.remove(at: index), index)
  }

  private func restoreCandidate(_ removed: (candidate: SuggestedCandidate, index: Int)) {
    guard !candidates.contains(where: { $0.id == removed.candidate.id }) else { return }
    insertCandidateBounded(removed.candidate, at: removed.index)
  }

  private func insertCandidateBounded(_ candidate: SuggestedCandidate, at requestedIndex: Int) {
    candidates.insert(candidate, at: min(max(0, requestedIndex), candidates.count))
    while candidates.count > Self.maxVisibleCandidates {
      let evicted = candidates.removeLast()
      recordsByID.removeValue(forKey: evicted.id)
      interventionIDs.removeValue(forKey: evicted.id)
      interventionAttributionChainIDs.removeValue(forKey: evicted.id)
    }
  }

  private func recordOrQueueFeedback(
    _ request: OmiAPI.FeedbackCreate,
    idempotencyKey: String,
    record: OmiAPI.CandidateRecord
  ) async -> OmiAPI.FeedbackRecord? {
    let suppressionOwnerID = activeSuppressionOwnerID
    let feedbackOwnerID = activeFeedbackOwnerID
    var preparedRequest = request
    let pendingInterventionRequest = Self.interventionRequest(for: record)
    upsertPendingFeedback(
      PendingSuggestedFeedback(
        request: request,
        idempotencyKey: idempotencyKey,
        accountGeneration: record.accountGeneration,
        interventionRequest: pendingInterventionRequest,
        interventionIdempotencyKey: Self.interventionIdempotencyKey(for: record)
      ))
    do {
      let intervention = try await ensureIntervention(
        for: record,
        request: pendingInterventionRequest
      )
      guard
        ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
      else {
        refreshOwnerScopedState()
        return nil
      }
      preparedRequest = Self.feedbackRequest(request, interventionID: intervention.interventionId)
      let feedback = try await client.recordTaskFeedback(
        preparedRequest, idempotencyKey: idempotencyKey, accountGeneration: record.accountGeneration
      )
      guard
        ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
      else {
        refreshOwnerScopedState()
        return nil
      }
      pendingFeedback.removeAll { $0.idempotencyKey == idempotencyKey }
      feedbackOutboxStore.save(pendingFeedback, ownerID: feedbackOwnerID)
      reportAttribution(
        .feedbackRecorded(
          interventionID: intervention.interventionId,
          surface: .suggested,
          action: preparedRequest.action.rawValue,
          reason: preparedRequest.reason?.rawValue,
          subjectKind: preparedRequest.subjectKind.rawValue,
          subjectID: preparedRequest.subjectId,
          candidateID: preparedRequest.subjectKind == .candidate ? preparedRequest.subjectId : nil,
          attributionChainID: feedback.attributionChainId
        ))
      return feedback
    } catch {
      guard
        ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
      else {
        refreshOwnerScopedState()
        return nil
      }
      upsertPendingFeedback(
        PendingSuggestedFeedback(
          request: preparedRequest,
          idempotencyKey: idempotencyKey,
          accountGeneration: record.accountGeneration,
          interventionRequest: preparedRequest.interventionId == nil
            ? pendingInterventionRequest : nil,
          interventionIdempotencyKey: preparedRequest.interventionId == nil
            ? Self.interventionIdempotencyKey(for: record) : nil
        ))
      self.error = "Saved. Feedback attribution will retry automatically."
      return nil
    }
  }

  private func upsertPendingFeedback(_ entry: PendingSuggestedFeedback) {
    pendingFeedback.removeAll { $0.idempotencyKey == entry.idempotencyKey }
    pendingFeedback.append(entry)
    feedbackOutboxStore.save(pendingFeedback, ownerID: activeFeedbackOwnerID)
  }

  private func retryPendingFeedback(ownerScope: OwnerScope, loadToken: UUID) async {
    let retryEntries = pendingFeedback
    var successfulKeys: Set<String> = []
    var failedByKey: [String: PendingSuggestedFeedback] = [:]
    for entry in retryEntries {
      guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
      var request = entry.request
      do {
        if request.interventionId == nil,
          let interventionRequest = entry.interventionRequest,
          let interventionKey = entry.interventionIdempotencyKey
        {
          let intervention = try await client.registerTaskIntervention(
            interventionRequest,
            idempotencyKey: interventionKey,
            accountGeneration: entry.accountGeneration
          )
          guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
          request = Self.feedbackRequest(request, interventionID: intervention.interventionId)
        }
        _ = try await client.recordTaskFeedback(
          request, idempotencyKey: entry.idempotencyKey, accountGeneration: entry.accountGeneration)
        guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
        successfulKeys.insert(entry.idempotencyKey)
      } catch {
        guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
        failedByKey[entry.idempotencyKey] = PendingSuggestedFeedback(
          request: request,
          idempotencyKey: entry.idempotencyKey,
          accountGeneration: entry.accountGeneration,
          interventionRequest: request.interventionId == nil ? entry.interventionRequest : nil,
          interventionIdempotencyKey: request.interventionId == nil
            ? entry.interventionIdempotencyKey : nil
        )
      }
    }
    guard loadScopeIsCurrent(ownerScope, token: loadToken) else { return }
    var merged = feedbackOutboxStore.load(ownerID: ownerScope.feedbackOwnerID)
      .filter { !successfulKeys.contains($0.idempotencyKey) }
    for failed in failedByKey.values {
      merged.removeAll { $0.idempotencyKey == failed.idempotencyKey }
      merged.append(failed)
    }
    pendingFeedback = merged
    feedbackOutboxStore.save(merged, ownerID: ownerScope.feedbackOwnerID)
  }

  private func ensureIntervention(
    for record: OmiAPI.CandidateRecord,
    request: OmiAPI.InterventionCreate? = nil
  ) async throws -> OmiAPI.InterventionRecord {
    if let existing = interventionIDs[record.candidateId] {
      return OmiAPI.InterventionRecord(
        attributionChainId: interventionAttributionChainIDs[record.candidateId]
          ?? "attribution-\(record.candidateId)",
        createdAt: record.createdAt,
        dedupeKey: Self.candidateRecommendationDedupeKey(record.candidateId),
        evidenceRefs: record.evidenceRefs,
        expiresAt: Self.deterministicInterventionExpiry(createdAt: record.createdAt),
        interventionId: existing,
        subjectId: record.candidateId,
        subjectKind: .candidate,
        surface: .suggested
      )
    }
    let suppressionOwnerID = activeSuppressionOwnerID
    let feedbackOwnerID = activeFeedbackOwnerID
    let intervention = try await client.registerTaskIntervention(
      request ?? Self.interventionRequest(for: record),
      idempotencyKey: Self.interventionIdempotencyKey(for: record),
      accountGeneration: record.accountGeneration
    )
    guard ownersAreCurrent(suppressionOwnerID: suppressionOwnerID, feedbackOwnerID: feedbackOwnerID)
    else {
      refreshOwnerScopedState()
      throw CancellationError()
    }
    interventionIDs[record.candidateId] = intervention.interventionId
    interventionAttributionChainIDs[record.candidateId] = intervention.attributionChainId
    return intervention
  }

  private static func interventionRequest(
    for record: OmiAPI.CandidateRecord
  ) -> OmiAPI.InterventionCreate {
    OmiAPI.InterventionCreate(
      dedupeKey: candidateRecommendationDedupeKey(record.candidateId),
      evidenceRefs: record.evidenceRefs,
      expiresAt: deterministicInterventionExpiry(createdAt: record.createdAt),
      subjectId: record.candidateId,
      subjectKind: .candidate,
      surface: .suggested
    )
  }

  static func candidateRecommendationDedupeKey(_ candidateID: String) -> String {
    let digest = SHA256.hash(data: Data(candidateID.utf8))
    let prefix = digest.prefix(16).map { String(format: "%02x", $0) }.joined()
    return "candidate_\(prefix)"
  }

  private static func deterministicInterventionExpiry(createdAt: String) -> String {
    let precise = ISO8601DateFormatter()
    precise.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let standard = ISO8601DateFormatter()
    standard.formatOptions = [.withInternetDateTime]
    let created = precise.date(from: createdAt) ?? standard.date(from: createdAt)
    let expiry = (created ?? Date(timeIntervalSince1970: 4_102_444_800))
      .addingTimeInterval(10 * 365 * 24 * 60 * 60)
    return iso8601(expiry)
  }

  private static func interventionIdempotencyKey(for record: OmiAPI.CandidateRecord) -> String {
    "suggested-presentation:\(record.candidateId)"
  }

  private static func feedbackRequest(
    _ request: OmiAPI.FeedbackCreate,
    interventionID: String
  ) -> OmiAPI.FeedbackCreate {
    OmiAPI.FeedbackCreate(
      action: request.action,
      contextSnapshotHash: request.contextSnapshotHash,
      interventionId: interventionID,
      laterUntil: request.laterUntil,
      reason: request.reason,
      subjectId: request.subjectId,
      subjectKind: request.subjectKind
    )
  }

  private static func project(_ record: OmiAPI.CandidateRecord) -> SuggestedCandidate? {
    guard record.status == nil || record.status == .pending else { return nil }
    if record.subjectKind == .task {
      guard record.proposedAction == .create, case .create = record.taskChange else { return nil }
    }
    let title = title(for: record)
    guard !title.isEmpty else { return nil }
    let detail = record.workstreamProposal?.objective
    return SuggestedCandidate(
      id: record.candidateId,
      title: title,
      detail: detail,
      provenanceLabel: provenanceLabel(for: record.sourceSurface),
      evidenceCount: record.evidenceRefs.count,
      accountGeneration: record.accountGeneration,
      isEditableTask: record.subjectKind == .task && record.proposedAction == .create,
      createdAt: record.createdAt
    )
  }

  private static func title(for record: OmiAPI.CandidateRecord) -> String {
    if let proposal = record.workstreamProposal { return proposal.title }
    switch record.taskChange {
    case .create(let task): return task.description_
    case .change(let task): return task.description_ ?? "Review a task update"
    case .none: return "Review suggested work"
    }
  }

  private static func provenanceLabel(for source: String) -> String {
    if source.contains("screen") { return "From your current context" }
    if source.contains("conversation") || source.contains("transcript") {
      return "From a conversation"
    }
    if source.contains("integration") || source.contains("email") { return "From a connected app" }
    return "Suggested by Omi"
  }

  private static func iso8601(_ date: Date) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: date)
  }

  func automationDump() -> [String: String] {
    [
      "count": String(candidates.count),
      "ids": candidates.map(\.id).joined(separator: ","),
    ]
  }

  func registerAutomationActions() {
    guard DesktopAutomationLaunchOptions.isEnabled, !didRegisterAutomationActions else { return }
    didRegisterAutomationActions = true
    DesktopAutomationActionRegistry.shared.register(
      name: "refresh_suggested_tasks",
      summary: "Refresh the canonical Suggested lane",
      params: []
    ) { [weak self] _ in
      guard let self else { return ["error": "suggested store deallocated"] }
      await self.load()
      return ["count": String(self.candidates.count), "error": self.error ?? ""]
    }
    DesktopAutomationActionRegistry.shared.register(
      name: "dump_suggested_tasks",
      summary: "Return privacy-safe Suggested candidate opaque ids",
      params: []
    ) { [weak self] _ in
      guard let self else { return ["error": "suggested store deallocated"] }
      return self.automationDump()
    }
    DesktopAutomationActionRegistry.shared.register(
      name: "suggested_task_action",
      summary: "Perform a Suggested card action through the real store",
      params: ["candidate_id", "action", "title", "reason"]
    ) { [weak self] params in
      guard let self else { return ["error": "suggested store deallocated"] }
      guard let candidateID = params["candidate_id"], !candidateID.isEmpty else {
        return ["error": "candidate_id is required"]
      }
      switch params["action"]?.lowercased() {
      case "do_now":
        let taskID = await self.doNow(candidateID: candidateID, editedTitle: params["title"])
        return self.automationResult(candidateID: candidateID, taskID: taskID)
      case "later":
        await self.later(candidateID: candidateID)
        return self.automationResult(candidateID: candidateID)
      case "dismiss":
        let reason: OmiAPI.TaskIntelligenceFeedbackReason?
        if let rawReason = params["reason"], !rawReason.isEmpty {
          guard let parsed = OmiAPI.TaskIntelligenceFeedbackReason(rawValue: rawReason),
            parsed != ._unknown
          else {
            return ["error": "reason must be already_handled, not_mine, or not_useful"]
          }
          reason = parsed
        } else {
          reason = nil
        }
        await self.dismiss(candidateID: candidateID, reason: reason)
        return self.automationResult(candidateID: candidateID)
      default:
        return ["error": "action must be do_now, later, or dismiss"]
      }
    }
  }

  private func automationResult(candidateID: String, taskID: String? = nil) -> [String: String] {
    [
      "candidate_id": candidateID,
      "remaining": candidates.contains(where: { $0.id == candidateID }) ? "true" : "false",
      "task_id": taskID ?? "",
      "error": error ?? "",
    ]
  }
}
