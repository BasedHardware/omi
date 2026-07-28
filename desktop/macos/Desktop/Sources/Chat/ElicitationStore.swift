import Combine
import Foundation

/// One option the agent offered. `id` is echoed back verbatim: for an ACP
/// permission it is the only answer the protocol accepts.
struct ElicitationOption: Identifiable, Equatable, Sendable {
  let id: String
  let label: String
  let effect: String

  /// Denial reads differently from approval, and the card styles it that way.
  var isRejection: Bool { effect.hasPrefix("reject") }
  /// A remembered grant outlives the turn that asked for it; the card says so.
  var isPermanent: Bool { effect.hasSuffix("always") }
}

/// A question waiting on the user, projected from a kernel dispatch.
///
/// `permission` and `question` differ in what the protocol beneath them can
/// carry, not merely in appearance: an ACP permission response may name only an
/// option the agent supplied, so that mode has no free-text answer at all.
struct PendingElicitation: Identifiable, Equatable, Sendable {
  enum Mode: String, Sendable {
    case permission
    case question
  }

  let id: String
  let ownerID: String
  let sessionID: String
  let runID: String?
  let mode: Mode
  let adapterID: String
  let title: String
  let prompt: String
  let subject: String?
  let context: String?
  let options: [ElicitationOption]
  let allowsFreeText: Bool
  /// Whether several options may be chosen. Never true for a permission: an ACP
  /// response names exactly one option, so a pick-many control there would build
  /// an answer the protocol cannot send.
  let allowsMultiple: Bool
  /// The option the source protocol marked as its recommended answer, when it
  /// named one. Advisory only: it is never staged or sent on the user's behalf,
  /// because a default that answers itself is not consent.
  let recommendedDefault: String?
  let createdAtMs: Double

  init?(payload: [String: Any]) {
    guard let id = payload["dispatchId"] as? String,
      let ownerID = payload["ownerId"] as? String,
      let sessionID = payload["sessionId"] as? String,
      let mode = (payload["mode"] as? String).flatMap(Mode.init(rawValue:)),
      let title = payload["title"] as? String,
      let prompt = payload["prompt"] as? String
    else { return nil }

    self.id = id
    self.ownerID = ownerID
    self.sessionID = sessionID
    self.runID = payload["runId"] as? String
    self.mode = mode
    self.adapterID = payload["adapterId"] as? String ?? "acp"
    self.title = title
    self.prompt = prompt
    self.subject = payload["subject"] as? String
    self.context = payload["context"] as? String
    self.options = (payload["options"] as? [[String: Any]] ?? []).compactMap { entry in
      guard let optionID = entry["optionId"] as? String else { return nil }
      return ElicitationOption(
        id: optionID,
        label: entry["label"] as? String ?? optionID,
        effect: entry["effect"] as? String ?? "choice"
      )
    }
    // A permission is answerable only by option id regardless of what the
    // payload claims, so the protocol constraint is re-asserted here rather
    // than trusted from the wire.
    self.allowsFreeText = mode == .question && (payload["allowsFreeText"] as? Bool ?? false)
    // Re-asserted here rather than trusted from the wire, for the same reason
    // as free text: the protocol constraint is ours to keep, not the sender's.
    self.allowsMultiple =
      mode == .question && (payload["allowsMultiple"] as? Bool ?? false) && !self.options.isEmpty
    // Only honoured when it names an option that was actually offered, so a
    // stale or malformed recommendation cannot mark a row the user cannot pick.
    let recommended = payload["recommendedDefault"] as? String
    self.recommendedDefault = self.options.contains { $0.id == recommended } ? recommended : nil
    self.createdAtMs = payload["createdAtMs"] as? Double ?? 0
  }
}

/// The user's answer, on its way back to the kernel.
enum ElicitationAnswer: Equatable, Sendable {
  /// The options the user chose, in the order the card offers them. A
  /// single-select question and every permission carry exactly one.
  case options([String])
  case text(String)
  case cancel
}

/// Holds the questions waiting on the user, oldest first.
///
/// Owns no truth: the kernel dispatch is authoritative and this is its
/// projection. Entries arrive and leave only through runtime messages, so a
/// card cannot outlive the dispatch it renders.
@MainActor
final class ElicitationStore: ObservableObject {
  /// Oldest first. The user reads them in this order but is not forced through
  /// it: any pending question can be brought forward.
  @Published private(set) var queue: [PendingElicitation] = []
  /// Which question the composer is showing.
  @Published private(set) var focusedID: String?
  /// Choices made but not yet sent, per question. Kept here rather than in the
  /// card so moving between questions does not discard what was already picked.
  @Published private(set) var staged: [String: ElicitationAnswer] = [:]

  var focused: PendingElicitation? {
    queue.first(where: { $0.id == focusedID }) ?? queue.first
  }
  var focusedIndex: Int {
    guard let focused else { return 0 }
    return queue.firstIndex(where: { $0.id == focused.id }) ?? 0
  }
  var waitingCount: Int { queue.count }
  var stagedForFocused: ElicitationAnswer? {
    focused.flatMap { staged[$0.id] }
  }

  func focus(_ elicitation: PendingElicitation) {
    guard queue.contains(where: { $0.id == elicitation.id }) else { return }
    focusedID = elicitation.id
  }

  func focusNext() { step(by: 1) }
  func focusPrevious() { step(by: -1) }

  private func step(by offset: Int) {
    guard queue.count > 1 else { return }
    let next = (focusedIndex + offset + queue.count) % queue.count
    focusedID = queue[next].id
  }

  /// Record a choice without sending it. Sending is a separate, explicit act so
  /// a mis-click is recoverable.
  func stage(_ answer: ElicitationAnswer, for elicitation: PendingElicitation) {
    guard queue.contains(where: { $0.id == elicitation.id }) else { return }
    staged[elicitation.id] = answer
  }

  func clearStaged(for elicitation: PendingElicitation) {
    staged[elicitation.id] = nil
  }

  /// Send what is staged for the question on screen.
  func submitFocused() {
    guard let focused, let pending = staged[focused.id] else { return }
    answer(focused, with: pending)
  }

  /// Finish the batch: every choice that was made is sent, and every question
  /// the user moved past without choosing is cancelled rather than left
  /// pending, since a question nobody answers blocks its agent forever.
  func submitAll() {
    for pending in queue {
      answer(pending, with: staged[pending.id] ?? .cancel)
    }
  }

  private let submit: (PendingElicitation, ElicitationAnswer) -> Void

  init(submit: @escaping (PendingElicitation, ElicitationAnswer) -> Void) {
    self.submit = submit
  }

  /// Ignores a duplicate id so a redelivered message cannot enqueue the same
  /// question twice.
  func enqueue(_ elicitation: PendingElicitation) {
    guard !queue.contains(where: { $0.id == elicitation.id }) else { return }
    queue.append(elicitation)
    if focusedID == nil { focusedID = elicitation.id }
  }

  /// Retires a question the kernel says is no longer pending, whoever ended it.
  /// Focus moves to whatever now occupies that position, so answering the last
  /// question in the queue does not leave the card pointing at nothing.
  func remove(id: String) {
    let index = queue.firstIndex(where: { $0.id == id })
    queue.removeAll { $0.id == id }
    staged[id] = nil
    guard focusedID == id else { return }
    guard let index, !queue.isEmpty else {
      focusedID = queue.first?.id
      return
    }
    focusedID = queue[min(index, queue.count - 1)].id
  }

  func answer(_ elicitation: PendingElicitation, with answer: ElicitationAnswer) {
    guard queue.contains(where: { $0.id == elicitation.id }) else { return }
    // Removed locally so the card leaves immediately; the kernel's own resolved
    // message is what makes it durable, and re-arrival is a no-op because
    // `remove` is idempotent.
    remove(id: elicitation.id)
    submit(elicitation, answer)
  }

  /// Drops everything for an owner that is no longer signed in. Signing back in
  /// as the same uid is a new authorization generation and must not inherit a
  /// question the previous one was asked.
  func clear(ownerID: String? = nil) {
    guard let ownerID else {
      queue.removeAll()
      staged.removeAll()
      focusedID = nil
      return
    }
    for dropped in queue where dropped.ownerID == ownerID { staged[dropped.id] = nil }
    queue.removeAll { $0.ownerID == ownerID }
    if queue.first(where: { $0.id == focusedID }) == nil { focusedID = queue.first?.id }
  }
}

/// Owns the elicitation queue and its runtime subscription.
///
/// Separated from `ChatProvider` so the provider holds one reference instead of
/// the store, its republishing observer, and the handler registration.
@MainActor
final class ElicitationProjection {
  let store: ElicitationStore
  private var republisher: AnyCancellable?
  init() {
    store = ElicitationStore { elicitation, answer in
      Task {
        await AgentRuntimeProcess.shared.resolveElicitation(
          dispatchID: elicitation.id,
          ownerID: elicitation.ownerID,
          answer: answer
        )
      }
    }
  }

  /// Subscribe to the runtime and republish queue changes.
  ///
  /// A nested `ObservableObject` does not publish through its parent, so
  /// without the republisher a view observing the provider never sees the card
  /// appear. `onChange` is the parent's `objectWillChange`.
  func start(onChange: @escaping () -> Void) {
    republisher = store.objectWillChange
      .receive(on: DispatchQueue.main)
      .sink { _ in onChange() }

    let store = store
    Task {
      await AgentRuntimeProcess.shared.setElicitationHandlers(
        pending: { elicitation in
          Task { @MainActor in store.enqueue(elicitation) }
        },
        resolved: { dispatchID in
          Task { @MainActor in store.remove(id: dispatchID) }
        }
      )
    }
  }
}

/// Pure wire shaping for elicitation messages.
///
/// Kept off the runtime actor so the actor holds only the effects — writing to
/// stdin and calling the projection handlers — and so the payload rules stay
/// directly testable without a subprocess.
enum ElicitationWire {
  /// What an inbound elicitation message means, once decoded.
  enum Inbound: Equatable {
    case pending(PendingElicitation)
    case resolved(dispatchID: String)
  }

  static func decodePending(_ payload: [String: Any]) -> Inbound? {
    guard let elicitation = PendingElicitation(payload: payload) else { return nil }
    return .pending(elicitation)
  }

  static func decodeResolved(_ payload: [String: Any]) -> Inbound? {
    guard let dispatchID = payload["dispatchId"] as? String else { return nil }
    return .resolved(dispatchID: dispatchID)
  }

  /// Build the answer message, or nil when the answering owner is not the owner
  /// that was asked. An answer under a different owner is refused rather than
  /// retargeted, so a question surviving an owner change cannot be resolved by
  /// whoever is signed in now.
  static func resolvePayload(
    dispatchID: String,
    ownerID: String,
    currentOwnerID: String?,
    answer: ElicitationAnswer
  ) -> [String: Any]? {
    guard let currentOwnerID, currentOwnerID == ownerID else { return nil }
    var payload: [String: Any] = [
      "type": "resolve_elicitation",
      "protocolVersion": 2,
      "ownerId": ownerID,
      "dispatchId": dispatchID,
    ]
    switch answer {
    case .options(let optionIDs):
      payload["decision"] = "answer"
      payload["optionIds"] = optionIDs
    case .text(let text):
      payload["decision"] = "answer"
      payload["text"] = text
    case .cancel:
      payload["decision"] = "cancel"
    }
    return payload
  }
}
