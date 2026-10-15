import Combine
import Foundation

/// A summary click uses the canonical Candidate owner, never the offline manual-task writer.
/// In-flight/error state is temporary; the saved conversation's targetTaskID is durable authority.
@MainActor
final class ConversationSummaryTaskPromoter: ObservableObject {
  struct Dependencies {
    var capture: @MainActor () -> RuntimeOwnerAuthorizationSnapshot?
    var isCurrent: @MainActor (RuntimeOwnerAuthorizationSnapshot) -> Bool
    var control: @MainActor (RuntimeOwnerAuthorizationSnapshot) async throws -> OmiAPI.TaskWorkflowControl
    var prepare:
      @MainActor (OmiAPI.SummaryTaskReference, String, Int, RuntimeOwnerAuthorizationSnapshot) async throws ->
        OmiAPI.CandidateRecord
    var accept:
      @MainActor (String, OmiAPI.SummaryTaskReference, Int, RuntimeOwnerAuthorizationSnapshot) async throws ->
        OmiAPI.CandidateResolutionReceipt

    static var live: Self {
      Self(
        capture: {
          guard AccountCutoverControlManager.shared.allowsOfflineQueueUpload else { return nil }
          return RuntimeOwnerIdentity.captureAuthorizationSnapshot()
        },
        isCurrent: { RuntimeOwnerIdentity.isAuthorizationCurrent($0) },
        control: { authorization in
          try await APIClient.shared.getCandidateWorkflowControl(
            expectedOwnerId: authorization.ownerID, authorizationSnapshot: authorization)
        },
        prepare: { selected, key, generation, authorization in
          try await APIClient.shared.prepareSummaryTask(
            selected, idempotencyKey: key, accountGeneration: generation, authorization: authorization)
        },
        accept: { candidateID, selected, generation, authorization in
          try await APIClient.shared.acceptSummaryTask(
            candidateID: candidateID, selected: selected, accountGeneration: generation, authorization: authorization)
        })
    }
  }

  @Published private(set) var adding: Set<Int> = []
  @Published private(set) var failed: Set<Int> = []
  @Published private(set) var error: String?
  private let dependencies: Dependencies

  init(dependencies: Dependencies = .live) { self.dependencies = dependencies }

  func promote(_ selected: OmiAPI.SummaryTaskReference) async -> String? {
    let index = selected.actionItemIndex
    guard !adding.contains(index) else { return nil }
    guard let authorization = dependencies.capture() else {
      failed.insert(index)
      error = "Your account is still syncing. Try adding this task again shortly."
      return nil
    }
    adding.insert(index)
    failed.remove(index)
    error = nil
    defer { adding.remove(index) }
    do {
      let control = try await dependencies.control(authorization)
      guard dependencies.isCurrent(authorization), !Task.isCancelled else { return nil }
      guard let generation = control.accountGeneration,
        control.workflowMode == .write || control.workflowMode == .read
      else { throw APIError.invalidResponse }
      let candidate = try await dependencies.prepare(
        selected, UUID().uuidString, generation, authorization)
      guard dependencies.isCurrent(authorization), !Task.isCancelled else { return nil }
      guard candidate.accountGeneration == generation else { throw APIError.invalidResponse }
      let receipt = try await dependencies.accept(
        candidate.candidateId, selected, generation, authorization)
      guard dependencies.isCurrent(authorization), !Task.isCancelled else { return nil }
      guard receipt.status == .accepted, let taskID = receipt.taskId else { throw APIError.invalidResponse }
      return taskID
    } catch {
      guard dependencies.isCurrent(authorization), !Task.isCancelled else { return nil }
      failed.insert(index)
      if case APIError.httpError(let status, _) = error, status == 409 || status == 404 {
        self.error = "This action item changed. Reopen the conversation before trying again."
      } else {
        self.error = "Could not add this task. Try again when you’re connected."
      }
      return nil
    }
  }

  static func linkedConversation(
    _ conversation: ServerConversation,
    selected: OmiAPI.SummaryTaskReference,
    taskID: String
  ) -> ServerConversation? {
    let index = selected.actionItemIndex
    guard conversation.id == selected.conversationId,
      conversation.structured.actionItems.indices.contains(index),
      conversation.structured.actionItems[index].description == selected.expectedDescription
    else { return nil }
    var items = conversation.structured.actionItems
    let item = items[index]
    items[index] = ActionItem(
      description: item.description, completed: item.completed, deleted: item.deleted,
      captureOwner: item.captureOwner, targetTaskID: taskID, sourceSegmentIDs: item.sourceSegmentIDs)
    let old = conversation.structured
    var linked = conversation
    linked.structured = Structured(
      title: old.title, overview: old.overview, emoji: old.emoji, category: old.category,
      actionItems: items, events: old.events, sections: old.sections)
    return linked
  }
}
