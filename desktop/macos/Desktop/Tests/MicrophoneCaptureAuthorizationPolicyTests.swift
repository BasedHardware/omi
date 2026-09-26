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

  func testAutomaticStartsNeverRequestOrSurfaceRegardlessOfStatus() {
    // The shared rule behind "skipped/denied permissions must not auto-reprompt":
    // launch, reactivation, key-load, settings-sync, wake, and post-onboarding
    // starts abandon instead of raising a sheet or an alert.
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .notDetermined, userInitiated: false),
      .abandonAutomaticStart)
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .denied, userInitiated: false),
      .abandonAutomaticStart)
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .restricted, userInitiated: false),
      .abandonAutomaticStart)
  }

  func testAutomaticStartsStillProceedWhenAuthorizedAndUserStartsKeepAsking() {
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .authorized, userInitiated: false),
      .proceed)
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .notDetermined, userInitiated: true),
      .requestPermission)
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .denied, userInitiated: true),
      .surfacePermissionAlert)
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
