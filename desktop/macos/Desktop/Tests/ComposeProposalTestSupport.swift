import AppKit
import XCTest

@testable import Omi_Computer

/// Stands in for Apple's compose windows so no test ever opens one.
@MainActor
final class FakeComposeSurface: ComposeSurface {
  var available = true
  var startSucceeds = true
  /// Reported from inside `present`, the way a window that answers at once would.
  var immediateEvent: ComposeSurfaceEvent?
  /// Runs as the window appears, before any report.
  var onPresent: (() -> Void)?
  private(set) var presented: [ComposeProposal] = []
  private var onEvent: (@MainActor (ComposeSurfaceEvent) -> Void)?

  func canPresent(_ proposal: ComposeProposal) -> Bool { available }

  func present(
    _ proposal: ComposeProposal,
    onEvent: @escaping @MainActor (ComposeSurfaceEvent) -> Void
  ) -> Bool {
    guard startSucceeds else { return false }
    presented.append(proposal)
    onPresent?()
    if let immediateEvent {
      onEvent(immediateEvent)
    } else {
      self.onEvent = onEvent
    }
    return true
  }

  func report(_ event: ComposeSurfaceEvent) {
    let callback = onEvent
    onEvent = nil
    callback?(event)
  }
}

/// Answers "seconds since the last key press" from a script, one value per poll.
@MainActor
final class ScriptedKeyboard {
  private var idleSeconds: [TimeInterval?]
  private(set) var polls = 0

  init(_ idleSeconds: [TimeInterval?]) { self.idleSeconds = idleSeconds }

  func secondsSinceLastKeyPress() -> TimeInterval? {
    polls += 1
    return idleSeconds.count > 1 ? idleSeconds.removeFirst() : idleSeconds.first ?? nil
  }
}

@MainActor
final class TaskHolder {
  var task: Task<String, Never>?
}

/// Shared fixtures for the compose proposal suites. It has no tests of its own.
@MainActor
class ComposeProposalTestCase: XCTestCase {
  let elapsesAtOnce: ComposeProposalCoordinator.Sleeper = { _ in }

  /// Suspends until the waiting task is cancelled, so only a window report can
  /// end the wait.
  let neverElapses: ComposeProposalCoordinator.Sleeper = { _ in
    let (stream, continuation) = AsyncStream<Void>.makeStream()
    for await _ in stream {}
    continuation.finish()
  }

  func context(run: String? = "run-1", owner: String? = "owner-1") -> ComposeProposalContext {
    ComposeProposalContext(runID: run, ownerID: owner)
  }

  func makeCoordinator(
    _ surface: FakeComposeSurface,
    sleep: @escaping ComposeProposalCoordinator.Sleeper,
    staleAfter: TimeInterval = ComposeProposalCoordinator.defaultStaleAfter,
    keyPress: @escaping () -> TimeInterval? = { nil },
    now: @escaping () -> Date = Date.init
  ) -> ComposeProposalCoordinator {
    ComposeProposalCoordinator(
      surface: surface, secondsSinceLastKeyPress: keyPress, staleAfter: staleAfter, sleep: sleep, now: now)
  }

  func emailProposal(_ to: [String] = ["sam@example.com"], body: String = "Here is the deck.") -> ComposeProposal {
    ComposeProposal(channel: .email, recipients: to, subject: "Deck", body: body)
  }

  func messageProposal(body: String = "On my way") -> ComposeProposal {
    ComposeProposal(channel: .message, recipients: ["+15550100100"], subject: nil, body: body)
  }

  func makeGrounding(account: String? = nil) -> ComposeRecipientGrounding {
    ComposeRecipientGrounding(accountEmail: { account })
  }

  func decode(_ json: String) throws -> [String: Any] {
    try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
  }
}
