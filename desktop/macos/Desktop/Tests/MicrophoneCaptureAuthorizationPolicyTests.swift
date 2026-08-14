import AVFoundation
import XCTest

@testable import Omi_Computer

/// Regression coverage for the microphone authorization gate (the "Microphone Isn't
/// Capturing Audio" loop): a denied or revoked TCC entry must surface the permission
/// alert instead of arming a zero-sample capture that ends in a hardware alert.
final class MicrophoneCaptureAuthorizationPolicyTests: XCTestCase {

  // MARK: - Capture-start gate

  func testAuthorizedProceedsToCapture() {
    XCTAssertEqual(MicrophoneCaptureAuthorizationPolicy.action(for: .authorized), .proceed)
  }

  func testNotDeterminedRequestsPermissionInsteadOfArmingCapture() {
    // First run: the HAL never prompts on its own, so the gate must.
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .notDetermined), .requestPermission)
  }

  func testDeniedSurfacesPermissionAlert() {
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .denied), .surfacePermissionAlert)
  }

  func testRestrictedSurfacesPermissionAlert() {
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .restricted), .surfacePermissionAlert)
  }

  func testDeclinedPermissionRequestSurfacesAlertNotCapture() {
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(afterRequestGranted: false),
      .surfacePermissionAlert)
  }

  func testGrantedPermissionRequestProceeds() {
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(afterRequestGranted: true), .proceed)
  }

  // MARK: - Exhausted-watchdog terminal alert

  func testExhaustedWatchdogBlamesPermissionWhenDenied() {
    // The revoked-mid-session case: capture was armed while authorized, TCC was revoked,
    // the watchdog exhausted its rebuilds on zero samples. The terminal alert must name
    // the permission, not the hardware.
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.terminalAlert(for: .denied), .permission)
  }

  func testExhaustedWatchdogBlamesPermissionWhenNotDetermined() {
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.terminalAlert(for: .notDetermined), .permission)
  }

  func testExhaustedWatchdogBlamesPermissionWhenRestricted() {
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.terminalAlert(for: .restricted), .permission)
  }

  func testExhaustedWatchdogBlamesHardwareOnlyWhenAuthorized() {
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.terminalAlert(for: .authorized), .hardware)
  }
}
