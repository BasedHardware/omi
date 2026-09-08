import XCTest

@testable import Omi_Computer

/// Where `Notification Delivery Skipped` is emitted from is the entire contract.
///
/// The first version of this event sat inside `deliverNotification`, which an
/// unauthorized notification never reaches: `sendNotification` returns at its
/// authorization guard first, and the context-director engines abort on a
/// non-`.queued` preflight. It compiled, its payload test passed, and it
/// emitted nothing for the population it was written to measure.
///
/// A behavioural test would be better, but `sendNotification` reads
/// authorization through `UserNotificationCallbackBridge.authorizationStatus`,
/// which has no injection seam, and adding one would change a production
/// signature to serve a test. Source inspection pins the property that actually
/// broke — placement — and would fail if the emit moved back behind a guard.
final class NotificationSkipEventPlacementTests: XCTestCase {
  private func notificationServiceSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent("ProactiveAssistants/Services/NotificationService.swift")
    // omi-test-quality: source-inspection -- static contract: pins which functions report an unauthorized drop
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  /// Body of `functionName`, from its declaration to the start of the next
  /// declaration at the same indentation.
  private func functionBody(_ functionName: String, in source: String) throws -> String {
    let lines = source.components(separatedBy: "\n")
    let startIndex = try XCTUnwrap(
      lines.firstIndex { $0.contains("func \(functionName)(") },
      "\(functionName) not found; if it was renamed, update this test rather than deleting it")
    let indent = lines[startIndex].prefix { $0 == " " }.count
    var endIndex = lines.count
    for index in (startIndex + 1)..<lines.count {
      let line = lines[index]
      guard !line.trimmingCharacters(in: .whitespaces).isEmpty else { continue }
      let lineIndent = line.prefix { $0 == " " }.count
      if lineIndent <= indent && line.contains("func ") {
        endIndex = index
        break
      }
    }
    return lines[startIndex..<endIndex].joined(separator: "\n")
  }

  private static let reporter = "reportUnauthorizedDrop"

  /// `sendNotification`'s authorization guard is the real drop for every
  /// assistant notification.
  func testSendNotificationReportsItsOwnUnauthorizedDrop() throws {
    let body = try functionBody("sendNotification", in: notificationServiceSource())
    XCTAssertTrue(
      body.contains(Self.reporter),
      "sendNotification returns before deliverNotification when unauthorized, so the drop must be reported here")
  }

  /// The context-director preflight is the real drop for that path: both
  /// engines abort unless it returns `.queued`, so anything reported after it
  /// is never reached.
  func testContextDirectorPreflightReportsItsOwnUnauthorizedDrop() throws {
    let body = try functionBody("contextDirectorPresentationPreflight", in: notificationServiceSource())
    XCTAssertTrue(
      body.contains(Self.reporter),
      "the engines bail on a non-.queued preflight, so an unauthorized drop must be reported inside it")
  }

  /// The regression itself: `deliverNotification` runs only *after* every
  /// authorization gate has passed, so an unauthorized drop can never be
  /// observed from there.
  func testDeliverNotificationDoesNotReportUnauthorizedDrops() throws {
    let body = try functionBody("deliverNotification", in: notificationServiceSource())
    XCTAssertFalse(
      body.contains(Self.reporter),
      "deliverNotification is past every authorization gate; reporting a drop here observes nothing")
  }

  /// Authorization must be its own guard, not folded into the alert-surface
  /// check — an alert style of `.none` is the user's own choice, and a
  /// permission that was never granted is not.
  func testPreflightSeparatesAuthorizationFromAlertStyle() throws {
    let body = try functionBody("contextDirectorPresentationPreflight", in: notificationServiceSource())
    let authorizationGate = try XCTUnwrap(
      body.range(of: "NotificationPermissionPolicy.isGranted"),
      "the preflight must check authorization on its own")
    let alertSurfaceGate = try XCTUnwrap(
      body.range(of: "hasVisibleAlertSurface"),
      "the preflight must still check the alert surface")
    XCTAssertTrue(
      authorizationGate.lowerBound < alertSurfaceGate.lowerBound,
      "authorization is checked first so a never-granted permission is not reported as a muted alert style")
  }
}
