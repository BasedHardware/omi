import XCTest

@testable import Omi_Computer

final class FocusLockTests: XCTestCase {
  func testPinsNormalizedWindowAndRejectsUnrelatedSources() throws {
    let source = try XCTUnwrap(FocusLockSource(appName: "Teams", windowTitle: "Planning"))
    let controller = FocusLockController()
    let now = Date(timeIntervalSince1970: 1_000)
    XCTAssertNotNil(controller.activate(source: source, duration: 15 * 60, now: now))

    XCTAssertTrue(controller.allows(appName: "Teams", windowTitle: "Planning", now: now))
    XCTAssertFalse(controller.allows(appName: "Slack", windowTitle: "Planning", now: now))
    XCTAssertFalse(controller.allows(appName: "Teams", windowTitle: "Other meeting", now: now))
    XCTAssertTrue(
      controller.allows(
        try XCTUnwrap(
          TaskLocalContextEvent.appWindow(
            appName: "Teams", windowTitle: "Planning", occurredAt: now)), now: now))
    XCTAssertFalse(
      controller.allows(
        try XCTUnwrap(
          TaskLocalContextEvent.appWindow(
            appName: "Slack", windowTitle: "DM", occurredAt: now)), now: now))
    XCTAssertFalse(
      controller.allows(
        try XCTUnwrap(
          TaskLocalContextEvent.normalized(
            kind: .meeting, rawReference: "Planning", occurredAt: now)), now: now))
  }

  func testExpiryReleaseAndReplacementRestoreNormalAdmission() throws {
    let controller = FocusLockController()
    let now = Date(timeIntervalSince1970: 2_000)
    let teams = try XCTUnwrap(FocusLockSource(appName: "Teams", windowTitle: "Planning"))
    let zoom = try XCTUnwrap(FocusLockSource(appName: "Zoom", windowTitle: nil))

    XCTAssertNil(controller.activate(source: teams, duration: 0, now: now))
    XCTAssertNotNil(controller.activate(source: teams, duration: 15 * 60, now: now))
    let firstRevision = controller.revision(now: now)
    XCTAssertNotNil(controller.activate(source: zoom, duration: 30 * 60, now: now))
    XCTAssertGreaterThan(controller.revision(now: now), firstRevision)
    XCTAssertTrue(controller.allows(appName: "Zoom", windowTitle: "Any call", now: now))
    XCTAssertFalse(controller.allows(appName: "Teams", windowTitle: "Planning", now: now))

    XCTAssertTrue(controller.release())
    XCTAssertTrue(controller.allows(appName: "Slack", windowTitle: "DM", now: now))
    XCTAssertFalse(controller.release())
    XCTAssertNotNil(controller.activate(source: teams, duration: 15 * 60, now: now))
    XCTAssertNil(controller.snapshot(now: now.addingTimeInterval(15 * 60)))
    XCTAssertTrue(controller.allows(appName: "Slack", windowTitle: "DM", now: now.addingTimeInterval(15 * 60)))
  }

  func testSourceTerminationReleasesOnlyMatchingApp() throws {
    let controller = FocusLockController()
    let source = try XCTUnwrap(FocusLockSource(appName: "Teams", windowTitle: "Planning"))
    XCTAssertNotNil(controller.activate(source: source, duration: 15 * 60))
    XCTAssertFalse(controller.releaseIfAppTerminated("Slack"))
    XCTAssertNotNil(controller.snapshot())
    XCTAssertTrue(controller.releaseIfAppTerminated("Teams"))
    XCTAssertNil(controller.snapshot())
  }

  func testClosedWindowNeverSilentlyRetargetsAnotherWindow() throws {
    let controller = FocusLockController()
    let now = Date(timeIntervalSince1970: 3_000)
    let source = try XCTUnwrap(FocusLockSource(appName: "Teams", windowTitle: "Planning"))
    XCTAssertNotNil(controller.activate(source: source, duration: 15 * 60, now: now))
    // The selected window may close while Teams itself remains open. In that
    // case the lock stays quiet until explicit release or the bounded expiry.
    XCTAssertFalse(
      controller.allows(
        appName: "Teams", windowTitle: "General chat", now: now.addingTimeInterval(60)))
    XCTAssertFalse(
      controller.allows(
        appName: "Slack", windowTitle: "DM", now: now.addingTimeInterval(60)))
    XCTAssertTrue(
      controller.allows(
        appName: "Slack", windowTitle: "DM", now: now.addingTimeInterval(15 * 60)))
  }

  func testAppWideLockAdmitsOnlyHashedEventsFromSameApp() throws {
    let controller = FocusLockController()
    let now = Date(timeIntervalSince1970: 4_000)
    let source = try XCTUnwrap(FocusLockSource(appName: "Teams", windowTitle: nil))
    _ = controller.activate(source: source, duration: 15 * 60, now: now)
    let teams = try XCTUnwrap(
      TaskLocalContextEvent.appWindow(
        appName: "Teams", windowTitle: "Planning", occurredAt: now))
    let otherTeams = try XCTUnwrap(
      TaskLocalContextEvent.appWindow(
        appName: "Teams", windowTitle: "Retrospective", occurredAt: now))
    let slack = try XCTUnwrap(
      TaskLocalContextEvent.appWindow(
        appName: "Slack", windowTitle: "DM", occurredAt: now))
    XCTAssertTrue(controller.allows(teams, now: now))
    XCTAssertTrue(controller.allows(otherTeams, now: now))
    XCTAssertFalse(controller.allows(slack, now: now))
    XCTAssertEqual(teams.appReferenceHash, otherTeams.appReferenceHash)
    XCTAssertNotEqual(teams.appReferenceHash, slack.appReferenceHash)
  }

  func testLifecycleTelemetryContainsOnlyBoundedFields() throws {
    let controller = FocusLockController()
    let now = Date(timeIntervalSince1970: 5_000)
    let source = try XCTUnwrap(
      FocusLockSource(
        appName: "Secret App", windowTitle: "Private client meeting"))
    _ = controller.activate(source: source, duration: 30 * 60, now: now)
    XCTAssertTrue(controller.release(reason: .manual))
    let events = controller.takeTelemetryEvents()
    XCTAssertEqual(events.map(\.eventName), ["Desktop Focus Lock Started", "Desktop Focus Lock Ended"])
    XCTAssertEqual(events[0].durationMinutes, 30)
    XCTAssertEqual(events[1].reason, .manual)
    XCTAssertEqual(Set(events[0].properties.keys), ["source_class", "duration_minutes"])
    XCTAssertEqual(Set(events[1].properties.keys), ["source_class", "duration_minutes", "release_reason"])
    XCTAssertFalse(String(describing: events.map(\.properties)).contains("Private client meeting"))
    XCTAssertFalse(String(describing: events.map(\.properties)).contains("Secret App"))
    XCTAssertTrue(controller.takeTelemetryEvents().isEmpty)
  }

  func testQueuedOutboxDeliveryIsFencedAcrossActivationAndRelease() throws {
    let controller = FocusLockController()
    let baseline = controller.revision()
    XCTAssertTrue(
      controller.allowsQueuedDelivery(
        appName: "Slack", windowTitle: "DM", revision: baseline))
    let source = try XCTUnwrap(FocusLockSource(appName: "Teams", windowTitle: "Planning"))
    _ = controller.activate(source: source, duration: 15 * 60)
    XCTAssertFalse(
      controller.allowsQueuedDelivery(
        appName: "Slack", windowTitle: "DM", revision: baseline))
    let lockedRevision = controller.revision()
    XCTAssertFalse(
      controller.allowsQueuedDelivery(
        appName: "Slack", windowTitle: "DM", revision: lockedRevision))
    XCTAssertTrue(
      controller.allowsQueuedDelivery(
        appName: "Teams", windowTitle: "Planning", revision: lockedRevision))
    _ = controller.release()
    XCTAssertFalse(
      controller.allowsQueuedDelivery(
        appName: "Teams", windowTitle: "Planning", revision: lockedRevision))
  }

  func testMemoryPresentationUsesCapturedSourceAndRejectsStaleGeneration() throws {
    let controller = FocusLockController()
    let source = try XCTUnwrap(FocusLockSource(appName: "Teams", windowTitle: "Planning"))
    let beforeLock = controller.revision()
    _ = controller.activate(source: source, duration: 15 * 60)
    let duringLock = controller.revision()
    XCTAssertFalse(
      controller.allowsCapturedResult(
        appName: "Slack", windowTitle: "DM", revision: duringLock))
    XCTAssertTrue(
      controller.allowsCapturedResult(
        appName: "Teams", windowTitle: "Planning", revision: duringLock))
    XCTAssertFalse(
      controller.allowsCapturedResult(
        appName: "Teams", windowTitle: "Planning", revision: beforeLock))
    XCTAssertFalse(
      controller.allowsCapturedResult(
        appName: nil, windowTitle: nil, revision: nil))
    _ = controller.release()
    XCTAssertFalse(
      controller.allowsCapturedResult(
        appName: "Teams", windowTitle: "Planning", revision: duringLock))
  }

  @MainActor
  func testPrivacyExclusionImmediatelyRevokesPinnedSource() throws {
    let app = "FocusLockPrivate-\(UUID().uuidString)"
    let controller = FocusLockController()
    let source = try XCTUnwrap(FocusLockSource(appName: app, windowTitle: "Document"))
    _ = controller.activate(source: source, duration: 15 * 60)
    XCTAssertNotNil(controller.snapshot())
    RewindSettings.shared.excludeApp(app)
    defer { RewindSettings.shared.includeApp(app) }
    XCTAssertNil(controller.snapshot())
    XCTAssertFalse(
      controller.allowsQueuedDelivery(
        appName: app, windowTitle: "Document", revision: 1))
    XCTAssertEqual(controller.takeTelemetryEvents().last?.reason, .privacyExcluded)
    XCTAssertNil(controller.activate(source: source, duration: 15 * 60))
  }
}
