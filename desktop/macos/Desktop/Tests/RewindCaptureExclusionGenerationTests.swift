import XCTest

@testable import Omi_Computer

final class RewindCaptureExclusionGenerationTests: XCTestCase {
  func testExclusionInvalidatesQueuedSnapshotAndReincludeStartsNewGeneration() {
    let appName = "RewindCaptureExclusionGenerationTests-\(UUID().uuidString)"
    let initial = RewindCaptureExclusionGeneration.snapshot(appName: appName)
    XCTAssertNotNil(initial)
    XCTAssertTrue(
      initial.map(RewindCaptureExclusionGeneration.isCurrent) ?? false)

    RewindCaptureExclusionGeneration.setExcluded(appName, excluded: true)
    XCTAssertFalse(
      initial.map(RewindCaptureExclusionGeneration.isCurrent) ?? true)
    XCTAssertNil(RewindCaptureExclusionGeneration.snapshot(appName: appName))

    RewindCaptureExclusionGeneration.setExcluded(appName, excluded: false)
    let resumed = RewindCaptureExclusionGeneration.snapshot(appName: appName)
    XCTAssertNotNil(resumed)
    XCTAssertNotEqual(initial?.generation, resumed?.generation)
    XCTAssertTrue(
      resumed.map(RewindCaptureExclusionGeneration.isCurrent) ?? false)
  }

  func testFinalizedChunkCleanupJournalIsOwnerScopedAndIdempotent() {
    let ownerA = "RewindCaptureExclusionGenerationTests-owner-a-\(UUID().uuidString)"
    let ownerB = "RewindCaptureExclusionGenerationTests-owner-b-\(UUID().uuidString)"
    let path = "2026-08-11/chunk-\(UUID().uuidString).mp4"

    RewindExcludedVideoChunkCleanupJournal.enqueue(relativePath: path, ownerID: ownerA)
    RewindExcludedVideoChunkCleanupJournal.enqueue(relativePath: path, ownerID: ownerA)
    XCTAssertEqual(
      RewindExcludedVideoChunkCleanupJournal.pending(ownerID: ownerA), [path])
    XCTAssertTrue(RewindExcludedVideoChunkCleanupJournal.pending(ownerID: ownerB).isEmpty)

    RewindExcludedVideoChunkCleanupJournal.complete(relativePath: path, ownerID: ownerA)
    XCTAssertTrue(RewindExcludedVideoChunkCleanupJournal.pending(ownerID: ownerA).isEmpty)
  }

  func testSupersededOwnerTransitionLeaseBecomesExclusion() throws {
    let ownerSnapshot = RewindCaptureOwnerSnapshot(
      ownerID: "lease-owner", generation: 1, authorizationSnapshot: nil)
    let snapshot = RewindCaptureExclusionSnapshot(
      appName: "Notes",
      generation: 1,
      ownerSnapshot: ownerSnapshot)
    let path = "2026-08-12/chunk-superseded.mp4"

    XCTAssertEqual(
      try RewindCaptureOwnerTransitionLease.resultOrExcluded(
        value: path,
        ownerTransitionQueued: false,
        relativePath: path,
        snapshot: snapshot),
      path)

    XCTAssertThrowsError(
      try RewindCaptureOwnerTransitionLease.resultOrExcluded(
        value: path,
        ownerTransitionQueued: true,
        relativePath: path,
        snapshot: snapshot)
    ) { error in
      let excluded = error as? RewindCaptureExcludedError
      XCTAssertEqual(excluded?.relativePath, path)
      XCTAssertEqual(excluded?.snapshot, snapshot)
    }
  }

  func testOwnerTransitionInvalidatesSameOwnerSessionAndRejectsDelayedEmbedding() async {
    await OCREmbeddingService.shared.reset()
    guard let ownerSnapshot = RewindCaptureOwnerSnapshot.capture() else {
      XCTFail("expected an active Rewind owner")
      return
    }

    RewindCaptureOwnerGeneration.beginTransition()
    XCTAssertFalse(ownerSnapshot.isCurrent())
    XCTAssertNil(RewindCaptureOwnerSnapshot.capture())
    await OCREmbeddingService.shared.embedScreenshot(
      id: 42,
      ocrText: "stale owner OCR text that must never enter the next owner batch",
      appName: "Example",
      windowTitle: "Private",
      ownerSnapshot: ownerSnapshot)
    let pendingCount = await OCREmbeddingService.shared.pendingCount
    XCTAssertEqual(pendingCount, 0)
    RewindCaptureOwnerGeneration.endTransition()

    guard let resumed = RewindCaptureOwnerSnapshot.capture() else {
      XCTFail("expected capture to resume")
      return
    }
    XCTAssertNotEqual(ownerSnapshot.generation, resumed.generation)
    XCTAssertTrue(resumed.isCurrent())
    await OCREmbeddingService.shared.reset()
  }

  /// #11572: launch / CI window where `auth_userId` is set but RewindDatabase
  /// has not resolved `currentUserId` yet. Capture preferred auth; isCurrent
  /// used to compare only the DB id and permanently fail-closed.
  ///
  /// #12039: establish the owner through the production transition boundary.
  /// Mutating `auth_userId` directly makes the process-wide authorization
  /// authority correctly revoke the out-of-band owner, so this test otherwise
  /// depends on which owner-bound suite ran before it.
  @MainActor
  func testOwnerSnapshotStaysCurrentWhenAuthLeadsUnresolvedRewindDatabase() async {
    let ownerFixture = RuntimeOwnerAuthorityTestFixture()
    addTeardownBlock { @MainActor in
      await ownerFixture.restore()
    }
    let previousDB = RewindDatabase.currentUserId
    defer {
      RewindDatabase.currentUserId = previousDB
    }

    // Reproduce the shared-state signature from #12039: another suite changed
    // durable auth outside the transition boundary, so the authorization
    // authority revoked itself before this test started.
    await ownerFixture.establish(authOwnerID: "prior-owner-\(UUID().uuidString)")
    UserDefaults.standard.set("out-of-band-owner-\(UUID().uuidString)", forKey: .authUserId)
    XCTAssertNil(RuntimeOwnerIdentity.captureAuthorizationSnapshot())

    let authOwner = "auth-leading-\(UUID().uuidString)"
    await ownerFixture.establish(authOwnerID: authOwner)
    RewindDatabase.currentUserId = nil

    guard let snapshot = RewindCaptureOwnerSnapshot.capture() else {
      XCTFail("expected capture with auth_userId set")
      return
    }
    XCTAssertEqual(snapshot.ownerID, authOwner)
    XCTAssertTrue(
      snapshot.isCurrent(),
      "auth-backed snapshot must stay current while RewindDatabase.currentUserId is still nil")
  }
}
