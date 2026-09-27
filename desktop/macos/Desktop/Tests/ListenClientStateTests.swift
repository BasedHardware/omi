import Combine
import XCTest

@testable import Omi_Computer

/// Behaviour of the /v4/listen `client_state` report: what counts as a visible live transcript.
@MainActor
final class ListenClientStateTests: XCTestCase {

  func testAShownSurfaceInAnActiveAppIsAVisibleTranscript() {
    let state = ListenClientState(foreground: true, observeApplication: false)
    let surface = UUID()

    state.setSurface(surface, visible: true)

    XCTAssertEqual(state.snapshot, .init(foreground: true, transcriptVisible: true))
    XCTAssertEqual(state.snapshot.jsonObject["type"] as? String, "client_state")
    XCTAssertEqual(state.snapshot.jsonObject["transcript_visible"] as? Bool, true)
  }

  func testDeactivatingTheAppHidesTheTranscriptAndReactivatingRestoresIt() {
    let state = ListenClientState(foreground: true, observeApplication: false)
    state.setSurface(UUID(), visible: true)

    state.setForeground(false)
    XCTAssertEqual(state.snapshot, .init(foreground: false, transcriptVisible: false))

    state.setForeground(true)
    XCTAssertEqual(state.snapshot, .init(foreground: true, transcriptVisible: true))
  }

  func testTheTranscriptStaysVisibleUntilTheLastSurfaceDisappears() {
    let state = ListenClientState(foreground: true, observeApplication: false)
    let card = UUID()
    let fullScreen = UUID()
    state.setSurface(card, visible: true)
    state.setSurface(fullScreen, visible: true)

    state.setSurface(card, visible: false)
    XCTAssertTrue(state.snapshot.transcriptVisible)

    state.setSurface(fullScreen, visible: false)
    state.setSurface(fullScreen, visible: false)
    XCTAssertFalse(state.snapshot.transcriptVisible)
  }

  func testSubscribersSeeOnlyRealChanges() {
    let state = ListenClientState(foreground: true, observeApplication: false)
    var received: [ListenClientState.Snapshot] = []
    let subscription = state.$snapshot.removeDuplicates().sink { received.append($0) }

    state.setForeground(true)  // unchanged
    let surface = UUID()
    state.setSurface(surface, visible: true)
    state.setSurface(surface, visible: true)  // unchanged
    state.setForeground(false)
    subscription.cancel()

    XCTAssertEqual(
      received,
      [
        .init(foreground: true, transcriptVisible: false),  // replayed on subscribe
        .init(foreground: true, transcriptVisible: true),
        .init(foreground: false, transcriptVisible: false),
      ])
  }
}
