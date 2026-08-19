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

  func testPendingContextBucketPurgeJournalIsOwnerScoped() {
    let ownerA = "pending-purge-owner-a-\(UUID().uuidString)"
    let ownerB = "pending-purge-owner-b-\(UUID().uuidString)"
    let appName = "SecretApp-\(UUID().uuidString)"

    RewindPendingContextBucketPurgeJournal.enqueue(appName: appName, ownerID: ownerA)
    XCTAssertEqual(
      RewindPendingContextBucketPurgeJournal.pending(ownerID: ownerA), [appName])
    XCTAssertTrue(
      RewindPendingContextBucketPurgeJournal.pending(ownerID: ownerB).isEmpty,
      "account B must not observe or clear account A's pending purge markers")

    RewindPendingContextBucketPurgeJournal.complete(appName: appName, ownerID: ownerB)
    XCTAssertEqual(
      RewindPendingContextBucketPurgeJournal.pending(ownerID: ownerA), [appName],
      "completing under a different owner must leave the originating marker intact")

    RewindPendingContextBucketPurgeJournal.complete(appName: appName, ownerID: ownerA)
    XCTAssertTrue(RewindPendingContextBucketPurgeJournal.pending(ownerID: ownerA).isEmpty)
  }

  func testLegacyPendingPurgeMarkersMigrateToActiveOwner() throws {
    let defaultsKey = "rewindPendingContextBucketPurges"
    let owner = "legacy-purge-owner-\(UUID().uuidString)"
    let names = ["SecretApp-\(UUID().uuidString)", "  Private App  "]
    let defaults = UserDefaults.standard
    let previous = defaults.object(forKey: defaultsKey)
    defer {
      if let previous {
        defaults.set(previous, forKey: defaultsKey)
      } else {
        defaults.removeObject(forKey: defaultsKey)
      }
    }
    defaults.set(names, forKey: defaultsKey)

    XCTAssertEqual(
      RewindPendingContextBucketPurgeJournal.pending(ownerID: owner),
      Set([names[0], "Private App"]))
    XCTAssertTrue(
      RewindPendingContextBucketPurgeJournal.pending(ownerID: "another-owner").isEmpty)
  }

  func testLegacyPendingPurgeMarkersMigrateOnEnqueueAndComplete() {
    let defaultsKey = "rewindPendingContextBucketPurges"
    let owner = "legacy-purge-owner-\(UUID().uuidString)"
    let legacyApp = "LegacyApp-\(UUID().uuidString)"
    let defaults = UserDefaults.standard
    let previous = defaults.object(forKey: defaultsKey)
    defer {
      if let previous {
        defaults.set(previous, forKey: defaultsKey)
      } else {
        defaults.removeObject(forKey: defaultsKey)
      }
    }
    defaults.set([legacyApp], forKey: defaultsKey)

    RewindPendingContextBucketPurgeJournal.enqueue(appName: "  \(legacyApp)  ", ownerID: owner)
    XCTAssertEqual(
      RewindPendingContextBucketPurgeJournal.pending(ownerID: owner), [legacyApp])

    RewindPendingContextBucketPurgeJournal.complete(appName: legacyApp, ownerID: owner)
    XCTAssertTrue(RewindPendingContextBucketPurgeJournal.pending(ownerID: owner).isEmpty)
  }

  @MainActor
  func testRearmPendingPurgeRetryRequiresCurrentOwner() async {
    let owner = "rearm-purge-owner-\(UUID().uuidString)"
    let defaults = UserDefaults.standard
    let previousOwner = defaults.object(forKey: .authUserId)
    defer {
      if let previousOwner {
        defaults.set(previousOwner, forKey: .authUserId)
      } else {
        defaults.removeObject(forKey: .authUserId)
      }
    }
    defaults.removeObject(forKey: .authUserId)

    let appName = "RearmApp-\(UUID().uuidString)"
    RewindPendingContextBucketPurgeJournal.enqueue(appName: appName, ownerID: owner)
    await RewindSettings.rearmPendingContextBucketPurgesForCurrentOwner()
    XCTAssertEqual(RewindPendingContextBucketPurgeJournal.pending(ownerID: owner), [appName])

    defaults.set(owner, forKey: .authUserId)
    await RewindSettings.rearmPendingContextBucketPurgesForCurrentOwner()
    // Without a live bucket store the purge fails closed and keeps the retry marker.
    XCTAssertEqual(RewindPendingContextBucketPurgeJournal.pending(ownerID: owner), [appName])
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
  func testOwnerSnapshotStaysCurrentWhenAuthLeadsUnresolvedRewindDatabase() {
    let defaults = UserDefaults.standard
    let previousAuth = defaults.object(forKey: .authUserId)
    let previousDB = RewindDatabase.currentUserId
    defer {
      if let previousAuth {
        defaults.set(previousAuth, forKey: .authUserId)
      } else {
        defaults.removeObject(forKey: .authUserId)
      }
      RewindDatabase.currentUserId = previousDB
    }

    let authOwner = "auth-leading-\(UUID().uuidString)"
    defaults.set(authOwner, forKey: .authUserId)
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
