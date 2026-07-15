import Foundation

/// One runtime callback, many surface projections. Runtime events are wakeups;
/// observers must range-fetch by turnSeq before mutating UI state.
@MainActor
final class KernelJournalEventHub {
  static let shared = KernelJournalEventHub()

  private struct Observer {
    let surfaceKey: String?
    let wake: @MainActor () -> Void
  }

  private var observers: [UUID: Observer] = [:]

  private init() {}

  func attach(client: AgentClient.Session) async {
    await client.setJournalTurnChangedHandler { turn in
      Task { @MainActor in
        KernelJournalEventHub.shared.publish(turn)
      }
    }
  }

  func attach(bridge: AgentBridge) async {
    await bridge.setJournalTurnChangedHandler { turn in
      Task { @MainActor in
        KernelJournalEventHub.shared.publish(turn)
      }
    }
  }

  func subscribe(surface: AgentSurfaceReference?, wake: @escaping @MainActor () -> Void) -> UUID {
    let token = UUID()
    observers[token] = Observer(surfaceKey: surface?.key, wake: wake)
    return token
  }

  func unsubscribe(_ token: UUID?) {
    guard let token else { return }
    observers.removeValue(forKey: token)
  }

  private func publish(_ turn: KernelJournalTurn) {
    let key = AgentSurfaceReference(
      surfaceKind: turn.surfaceKind,
      externalRefKind: turn.externalRefKind,
      externalRefId: turn.externalRefId
    ).key
    for observer in observers.values where observer.surfaceKey == nil || observer.surfaceKey == key {
      observer.wake()
    }
  }
}
