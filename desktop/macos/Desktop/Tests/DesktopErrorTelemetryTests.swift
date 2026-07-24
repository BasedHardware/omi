import Foundation
import XCTest

@testable import Omi_Computer

final class DesktopErrorTelemetryTests: XCTestCase {
  func testMissingErrorGetsBoundedCompileTimeOwnership() {
    let descriptor = DesktopErrorTelemetryDescriptor.make(
      error: nil,
      fileID: "Omi_Computer/AudioCaptureService.swift")

    XCTAssertEqual(descriptor.area, "audio")
    XCTAssertEqual(descriptor.failureClass, "missing_underlying_error")
    XCTAssertEqual(descriptor.phase, "runtime")
    XCTAssertEqual(descriptor.errorType, "none")
    XCTAssertEqual(descriptor.errorDomain, "none")
    XCTAssertEqual(descriptor.errorCode, "none")
    XCTAssertEqual(descriptor.eventTitle, "Desktop error [audio/missing_underlying_error/runtime]")
  }

  func testNSErrorMetadataIsNormalizedToBoundedFamilies() {
    let descriptor = DesktopErrorTelemetryDescriptor.make(
      error: NSError(domain: NSPOSIXErrorDomain, code: 49),
      fileID: "Omi_Computer/FloatingControlBar/RealtimeHubController.swift")

    XCTAssertEqual(descriptor.area, "realtime")
    XCTAssertEqual(descriptor.failureClass, "underlying_error")
    XCTAssertEqual(descriptor.errorType, "posix")
    XCTAssertEqual(descriptor.errorDomain, "posix")
    XCTAssertEqual(descriptor.errorCode, "49")
  }

  func testUnknownNSErrorMetadataCannotCreateHighCardinalityTags() {
    let descriptor = DesktopErrorTelemetryDescriptor.make(
      error: NSError(domain: "customer-generated-\(UUID().uuidString)", code: Int.max),
      fileID: "Omi_Computer/UnknownFeature.swift")

    XCTAssertEqual(descriptor.area, "other")
    XCTAssertEqual(descriptor.errorType, "other")
    XCTAssertEqual(descriptor.errorDomain, "other")
    XCTAssertEqual(descriptor.errorCode, "other")
  }
}
