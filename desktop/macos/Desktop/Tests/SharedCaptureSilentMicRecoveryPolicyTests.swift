import XCTest

@testable import Omi_Computer

final class SharedCaptureSilentMicRecoveryPolicyTests: XCTestCase {
  func testConfiguresNonBluetoothInputsForSilentCaptureDetection() {
    let capture = AudioCaptureService()
    SharedCaptureSilentMicRecoveryPolicy.configure(capture)

    XCTAssertNil(capture.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 0))
    XCTAssertNotNil(capture.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 1))
  }

  func testRebuildsBeforeTheBoundedRecoveryLimit() {
    XCTAssertEqual(SharedCaptureSilentMicRecoveryPolicy.action(for: 1), .rebuild)
    XCTAssertEqual(SharedCaptureSilentMicRecoveryPolicy.action(for: 2), .rebuild)
  }

  func testStopsAndSurfacesErrorAtTheRecoveryLimit() {
    XCTAssertEqual(
      SharedCaptureSilentMicRecoveryPolicy.action(for: 3),
      .stopAndSurfaceError)
  }
}
