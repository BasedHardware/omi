import XCTest

@testable import Omi_Computer

@MainActor
final class VoiceResponsePlaybackTests: XCTestCase {
  func testInterruptWhenIdleReturnsFalse() {
    VoiceResponsePlaybackMonitor.shared.refresh()
    XCTAssertFalse(VoiceResponsePlayback.isActive)
    XCTAssertFalse(VoiceResponsePlayback.interrupt())
    XCTAssertFalse(VoiceResponsePlaybackMonitor.shared.isActive)
  }
}
