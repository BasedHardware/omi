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

  func testSurfaceReportingURLAcceptsBothBackendBaseShapes() {
    for base in ["https://backend.example.invalid", "https://backend.example.invalid/"] {
      XCTAssertEqual(
        ListenClientState.surfaceReportURL(baseURL: base)?.absoluteString,
        "https://backend.example.invalid/v1/users/client-state")
    }
  }

  func testOcclusionDuringHeaderPreparationReadsLatestStateAndDrainsClose() async {
    var open = true
    var release: CheckedContinuation<Void, Never>?
    let preparing = expectation(description: "Preparing headers")
    var sent: [Bool] = []
    let state = ListenClientState(
      foreground: true, observeApplication: false, surfaceReportingEnabled: true,
      surfaceOpen: { open },
      surfaceTransport: { latest in
        if sent.isEmpty {
          await withCheckedContinuation { continuation in
            release = continuation
            preparing.fulfill()
          }
        }
        sent.append(try XCTUnwrap(latest()["surface_open"] as? Bool))
        return true
      })
    state.reportSurface()
    await fulfillment(of: [preparing])
    open = false
    state.reportSurface()
    release?.resume()
    await state.waitForSurfaceReportsForTest()
    XCTAssertEqual(sent, [false, false])
  }

  func testCloseWhileOpenIsOnTheWireIsSentImmediatelyAfterIt() async {
    await assertCloseDrains(openDelivered: true)
  }

  func testQueuedCloseIsSentEvenWhenTheOpenFails() async {
    await assertCloseDrains(openDelivered: false)
  }

  private func assertCloseDrains(openDelivered: Bool) async {
    var open = true
    var release: CheckedContinuation<Void, Never>?
    let transmitting = expectation(description: "Open on wire")
    var sent: [Bool] = []
    let state = ListenClientState(
      foreground: true, observeApplication: false, surfaceReportingEnabled: true,
      surfaceOpen: { open },
      surfaceTransport: { latest in
        sent.append(try XCTUnwrap(latest()["surface_open"] as? Bool))
        if sent.count == 1 {
          await withCheckedContinuation { continuation in
            release = continuation
            transmitting.fulfill()
          }
        }
        return sent.count == 1 ? openDelivered : true
      })
    state.reportSurface(heartbeat: true)
    await fulfillment(of: [transmitting])
    open = false
    state.reportSurface()
    release?.resume()
    await state.waitForSurfaceReportsForTest()
    XCTAssertEqual(sent, [true, false])
  }

  func testFailedCloseIsRetriedByClosedHeartbeatWithoutSpinning() async {
    var open = true
    var failClose = true
    var sent: [Bool] = []
    let state = ListenClientState(
      foreground: true, observeApplication: false, surfaceReportingEnabled: true,
      surfaceOpen: { open },
      surfaceTransport: { latest in
        let value = try XCTUnwrap(latest()["surface_open"] as? Bool)
        sent.append(value)
        if !value && failClose { throw URLError(.timedOut) }
        return true
      })
    state.reportSurface()
    await state.waitForSurfaceReportsForTest()
    open = false
    state.reportSurface()
    await state.waitForSurfaceReportsForTest()
    XCTAssertEqual(sent, [true, false])
    failClose = false
    state.reportSurface(heartbeat: true)
    await state.waitForSurfaceReportsForTest()
    XCTAssertEqual(sent, [true, false, false])
    state.reportSurface(heartbeat: true)
    await state.waitForSurfaceReportsForTest()
    XCTAssertEqual(sent.count, 3)
  }

}
