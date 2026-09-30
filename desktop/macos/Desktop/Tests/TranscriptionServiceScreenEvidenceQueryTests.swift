import Foundation
import XCTest

@testable import Omi_Computer

/// The `/v4/listen` declaration the backend's notes admission keys on: only a meeting whose
/// screenshots are on runs the pre-notes evidence pass, so only that session may ask the server to
/// wait for it.
final class TranscriptionServiceScreenEvidenceQueryTests: XCTestCase {
  func testOnlyMeetingsWithScreenshotsOnDeclareTheEvidencePass() {
    XCTAssertEqual(
      TranscriptionService.screenEvidenceQueryItems(role: .meeting, screenshotsEnabled: true),
      [URLQueryItem(name: "screen_evidence", value: "enabled")])
    XCTAssertEqual(TranscriptionService.screenEvidenceQueryItems(role: .meeting, screenshotsEnabled: false), [])
    XCTAssertEqual(TranscriptionService.screenEvidenceQueryItems(role: .ambient, screenshotsEnabled: true), [])
  }
}
