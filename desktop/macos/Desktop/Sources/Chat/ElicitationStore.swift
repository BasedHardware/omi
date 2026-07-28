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
    self.createdAtMs = payload["createdAtMs"] as? Double ?? 0
  }
}

/// The user's answer, on its way back to the kernel.
enum ElicitationAnswer: Equatable, Sendable {
  case option(String)
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
  /// FIFO. Only the head is presented; the rest wait their turn, because the
  /// composer has exactly one slot and answering out of order would make the
  /// count meaningless.
  @Published private(set) var queue: [PendingElicitation] = []

  var current: PendingElicitation? { queue.first }
  var waitingCount: Int { queue.count }

  private let submit: (PendingElicitation, ElicitationAnswer) -> Void

  init(submit: @escaping (PendingElicitation, ElicitationAnswer) -> Void) {
    self.submit = submit
  }

  /// Ignores a duplicate id so a redelivered message cannot enqueue the same
  /// question twice.
  func enqueue(_ elicitation: PendingElicitation) {
    guard !queue.contains(where: { $0.id == elicitation.id }) else { return }
    queue.append(elicitation)
  }

  /// Retires a question the kernel says is no longer pending, whoever ended it.
  func remove(id: String) {
    queue.removeAll { $0.id == id }
  }

  func answer(_ elicitation: PendingElicitation, with answer: ElicitationAnswer) {
    guard queue.contains(where: { $0.id == elicitation.id }) else { return }
    // Removed locally so the card leaves immediately on click; the kernel's
    // own resolved message is what makes it durable, and re-arrival is a no-op
    // because `remove` is idempotent.
    queue.removeAll { $0.id == elicitation.id }
    submit(elicitation, answer)
  }

  /// Drops everything for an owner that is no longer signed in. Signing back in
  /// as the same uid is a new authorization generation and must not inherit a
  /// question the previous one was asked.
  func clear(ownerID: String? = nil) {
    guard let ownerID else {
      queue.removeAll()
      return
    }
    queue.removeAll { $0.ownerID == ownerID }
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
