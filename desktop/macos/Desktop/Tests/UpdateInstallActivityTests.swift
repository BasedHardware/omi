import XCTest

@testable import Omi_Computer

@MainActor
final class UpdateInstallActivityTests: XCTestCase {
  override func setUp() {
    super.setUp()
    UpdateInstallActivity.resetForTesting()
  }

  override func tearDown() {
    UpdateInstallActivity.resetForTesting()
    super.tearDown()
  }

  func testNoCaptureMeansNoActivity() {
    XCTAssertNil(UpdateInstallActivity.lastActivityAt(now: Date(timeIntervalSince1970: 1_000)))
  }

  func testTranscriptActivityIsReportedAtItsOwnTime() {
    let spoke = Date(timeIntervalSince1970: 900)
    UpdateInstallActivity.markTranscriptActivity(at: spoke)
    XCTAssertEqual(UpdateInstallActivity.lastActivityAt(now: Date(timeIntervalSince1970: 1_000)), spoke)
  }

  func testMeetingCaptureIsActiveNowThroughQuietStretches() {
    let now = Date(timeIntervalSince1970: 1_000)
    UpdateInstallActivity.markTranscriptActivity(at: Date(timeIntervalSince1970: 100))
    UpdateInstallActivity.setMeetingCaptureActive(true)
    XCTAssertEqual(UpdateInstallActivity.lastActivityAt(now: now), now)
    UpdateInstallActivity.setMeetingCaptureActive(false)
    XCTAssertEqual(UpdateInstallActivity.lastActivityAt(now: now), Date(timeIntervalSince1970: 100))
  }

  func testAppStatePublishesMeetingCaptureOnlyWhileLiveCapturing() {
    let state = AppState()
    let now = Date(timeIntervalSince1970: 1_000)
    state.currentConversationRole = .meeting
    XCTAssertNil(UpdateInstallActivity.lastActivityAt(now: now), "a meeting role without capture is not active")

    state.isTranscribing = true
    XCTAssertEqual(UpdateInstallActivity.lastActivityAt(now: now), now)

    state.currentConversationRole = .ambient
    XCTAssertNil(UpdateInstallActivity.lastActivityAt(now: now))

    state.currentConversationRole = .meeting
    state.isAwaitingMeeting = true
    XCTAssertNil(UpdateInstallActivity.lastActivityAt(now: now), "a paused Only-Meetings mic captures nothing")

    state.isAwaitingMeeting = false
    XCTAssertEqual(UpdateInstallActivity.lastActivityAt(now: now), now)

    state.isTranscribing = false
    XCTAssertNil(UpdateInstallActivity.lastActivityAt(now: now))
  }
}
