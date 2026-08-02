import Foundation
import XCTest

@testable import Omi_Computer

private final class SuspendedPhysicalStopCapture: AudioCaptureService, @unchecked Sendable {
  private let lock = NSLock()
  private var events: [String] = []
  private let waitStarted = TestAsyncGate()
  private let mayFinish = TestAsyncGate()

  override func stopCapture() {
    lock.withLock { events.append("stop") }
  }

  override func waitForPhysicalStop() async {
    lock.withLock { events.append("wait") }
    await waitStarted.open()
    await mayFinish.wait()
  }

  func waitUntilPhysicalStopIsAwaited() async {
    await waitStarted.wait()
  }

  func finishPhysicalStop() async {
    await mayFinish.open()
  }

  func recordedEvents() -> [String] {
    lock.withLock { events }
  }
}

@MainActor
final class TranscriptionSettingsRestartTests: XCTestCase {
  func testSettingsRestartWaitsForPhysicalMicStopBeforeStartingAgain() async {
    let state = AppState()
    let capture = SuspendedPhysicalStopCapture()
    state.audioCaptureService = capture
    state.isTranscribing = true
    state.sttSession.activeMode = .local
    var events: [String] = []

    let restart = Task { @MainActor in
      if await state.prepareTranscriptionRestartAfterSettingsChange() {
        events.append("start")
      }
    }

    await capture.waitUntilPhysicalStopIsAwaited()
    XCTAssertEqual(capture.recordedEvents(), ["stop", "wait"])
    XCTAssertTrue(events.isEmpty)

    await capture.finishPhysicalStop()
    await restart.value

    XCTAssertEqual(events, ["start"])
  }

  func testSettingsRestartDoesNotReopenAfterUserStopsAgainDuringTeardown() async {
    let state = AppState()
    let capture = SuspendedPhysicalStopCapture()
    state.audioCaptureService = capture
    state.isTranscribing = true
    state.sttSession.activeMode = .local
    var restarted = false

    let restart = Task { @MainActor in
      if await state.prepareTranscriptionRestartAfterSettingsChange() {
        restarted = true
      }
    }

    await capture.waitUntilPhysicalStopIsAwaited()
    let userStop = state.stopTranscription()
    await userStop?.value
    await capture.finishPhysicalStop()
    await restart.value

    XCTAssertFalse(restarted)
  }
}
