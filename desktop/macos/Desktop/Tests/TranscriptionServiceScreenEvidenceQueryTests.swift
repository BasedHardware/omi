import Foundation
import XCTest

@testable import Omi_Computer

/// The `/v4/listen` declaration the backend's notes admission keys on: only a meeting whose
/// screenshots are on runs the pre-notes evidence pass, so only that session may ask the server to
/// wait for it.
final class TranscriptionServiceScreenEvidenceQueryTests: XCTestCase {
  func testMeetingTimeoutCoversSustainAndResumeWithoutLeavingAnOrphanForFourHours() {
    XCTAssertEqual(
      TranscriptionService.conversationLifetimeQueryItems(role: .meeting),
      [URLQueryItem(name: "conversation_timeout", value: "600")])
    XCTAssertGreaterThan(
      MeetingDetectionTiming.conversationTimeout,
      MeetingDetectionTiming.inputOnlySustainPeriod + 8 + MeetingDetectionTiming.resumeWindow)
    XCTAssertLessThan(MeetingDetectionTiming.conversationTimeout, 4 * 60 * 60)
  }

  func testAmbientKeepsTheBackendDefaultLifetime() {
    XCTAssertEqual(TranscriptionService.conversationLifetimeQueryItems(role: .ambient), [])
  }

  func testOnlyMeetingsWithScreenshotsOnDeclareTheEvidencePass() {
    XCTAssertEqual(
      TranscriptionService.screenEvidenceQueryItems(role: .meeting, screenshotsEnabled: true),
      [URLQueryItem(name: "screen_evidence", value: "enabled")])
    XCTAssertEqual(TranscriptionService.screenEvidenceQueryItems(role: .meeting, screenshotsEnabled: false), [])
    XCTAssertEqual(TranscriptionService.screenEvidenceQueryItems(role: .ambient, screenshotsEnabled: true), [])
  }
}
