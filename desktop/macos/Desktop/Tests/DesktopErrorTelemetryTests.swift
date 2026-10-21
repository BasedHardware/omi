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

  func testOnboardingCallSitesProduceDistinguishableBoundedSites() {
    let sound = DesktopErrorTelemetryDescriptor.make(
      error: NSError(domain: "com.omi.onboarding", code: 1),
      fileID: "Omi_Computer/Onboarding/Cinematic/OmiOnboardingSound.swift",
      function: "startEngine()")
    let chat = DesktopErrorTelemetryDescriptor.make(
      error: NSError(domain: "com.omi.onboarding", code: 1),
      fileID: "Omi_Computer/Onboarding/OnboardingChatView.swift",
      function: "createGoalFromOnboardingInput()")

    XCTAssertEqual(sound.area, "onboarding")
    XCTAssertEqual(chat.area, "onboarding")
    XCTAssertEqual(sound.site, "omionboardingsound.startengine")
    XCTAssertEqual(chat.site, "onboardingchatview.creategoalfromonboardinginput")
    XCTAssertNotEqual(sound.eventTitle, chat.eventTitle)
    XCTAssertTrue(sound.eventTitle.contains(sound.site))
    XCTAssertTrue(chat.eventTitle.contains(chat.site))
    XCTAssertFalse(sound.site.contains("/"))
    XCTAssertFalse(chat.site.contains("/"))
    XCTAssertEqual(sound.errorType, "app")
    XCTAssertEqual(sound.errorDomain, "app")
  }

  func testErrorSiteStripsPathsAndDoesNotCarryMessages() {
    let message = "import failed for user \(UUID().uuidString) at /Users/omi/secret.json"
    let descriptor = DesktopErrorTelemetryDescriptor.make(
      error: NSError(
        domain: NSPOSIXErrorDomain, code: 1,
        userInfo: [
          NSLocalizedDescriptionKey: message
        ]),
      fileID: "Omi_Computer/Onboarding/OnboardingPagedIntroCoordinator.swift",
      function: "savePrimaryLanguage()")

    XCTAssertEqual(descriptor.site, "onboardingpagedintrocoordinator.saveprimarylanguage")
    XCTAssertFalse(descriptor.site.contains("Users"))
    XCTAssertFalse(descriptor.site.contains("secret"))
    XCTAssertFalse(descriptor.eventTitle.contains(message))
    XCTAssertFalse(descriptor.eventTitle.contains("/Users"))
    for field in [
      descriptor.area, descriptor.failureClass, descriptor.phase, descriptor.errorType,
      descriptor.errorDomain, descriptor.errorCode, descriptor.site,
    ] {
      XCTAssertFalse(field.contains("/"))
      XCTAssertFalse(field.contains(message))
    }
  }

  func testAppModuleSwiftErrorReportsBoundedTypeNameInsteadOfOther() {
    let descriptor = DesktopErrorTelemetryDescriptor.make(
      error: DesktopErrorTelemetryAppModuleProbe.fixture,
      fileID: "Omi_Computer/Onboarding/OnboardingPagedIntroCoordinator.swift",
      function: "saveOnboardingGoal()")

    XCTAssertEqual(descriptor.errorType, "desktoperrortelemetryappmoduleprobe")
    XCTAssertNotEqual(descriptor.errorType, "other")
    XCTAssertFalse(descriptor.errorType.contains("."))
  }

  func testStorageDiagnosticsExposeMeasurementsWithoutThePath() throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("storage-diagnostics-\(UUID().uuidString)", isDirectory: true)
    let database = directory.appendingPathComponent("omi.db")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    try Data(repeating: 7, count: 32).write(to: database)
    defer { try? FileManager.default.removeItem(at: directory) }

    let context = StorageFailureDiagnostics.context(
      pathClass: "rewind-db",
      containingURL: directory,
      databaseURL: database,
      error: NSError(domain: NSPOSIXErrorDomain, code: 28),
      appIsTerminating: true)

    XCTAssertEqual(context.values["path_class"] as? String, "rewind-db")
    XCTAssertEqual(context.values["database_file_size_bytes"] as? Int64, 32)
    XCTAssertEqual(context.values["error_domain"] as? String, NSPOSIXErrorDomain)
    XCTAssertEqual(context.values["error_code"] as? Int, 28)
    XCTAssertEqual(context.values["app_terminating"] as? Bool, true)
    XCTAssertFalse(context.values.values.contains { "\($0)".contains(directory.path) })
  }

  func testBridgeStartDiagnosticsSeparatesTimeoutFromSpawnPreconditions() {
    let context = AgentRuntimeProcess.startFailureDiagnostics(
      failure: .handshakeTimedOut,
      elapsedMs: 30_000,
      exitCode: nil,
      binaryPresent: true,
      binaryPresentChecked: true,
      permissionGrantedChecked: true,
      permissionGranted: false)

    XCTAssertEqual(context.values["startup_stage"] as? String, "handshake_timed_out")
    XCTAssertEqual(context.values["configured_timeout_ms"] as? Int, 30_000)
    XCTAssertEqual(context.values["binary_present_checked"] as? Bool, true)
    XCTAssertEqual(context.values["binary_present"] as? Bool, true)
    XCTAssertEqual(context.values["permission_granted"] as? Bool, false)
    XCTAssertEqual(context.values["port_bound_checked"] as? Bool, false)
  }

  func testBridgeStartDiagnosticsDoesNotClaimBinaryProbeBeforeItRuns() {
    let context = AgentRuntimeProcess.startFailureDiagnostics(
      failure: .launchFailed,
      elapsedMs: 12,
      exitCode: nil,
      binaryPresent: false,
      binaryPresentChecked: false,
      permissionGrantedChecked: false,
      permissionGranted: false)

    XCTAssertEqual(context.values["binary_present_checked"] as? Bool, false)
    XCTAssertEqual(context.values["binary_present"] as? Bool, false)
  }
}
