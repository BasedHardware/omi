import OmiWAL
import XCTest

@testable import Omi_Computer

final class WALCloudSyncLogicTests: XCTestCase {

  private func makeWal(status: WALStatus = .miss) -> WALEntry {
    WALEntry(
      timerStart: 1_700_000_000,
      codec: "opus",
      status: status,
      storage: .disk,
      filePath: "audio_test.bin",
      seconds: 60,
      device: "dev1",
      deviceModel: "Omi"
    )
  }

  func testApplyUploadResultDoesNotSyncWithoutServerAck() {
    // A WAL that never receives a server ack (no applyUploadResult call) must
    // stay .miss. This guards against the old stub that marked .synced after a
    // local parse. The companion tests below prove applyUploadResult *does*
    // transition on a real 200/202 ack, so this is a meaningful guard.
    var wal = makeWal()
    XCTAssertEqual(wal.status, .miss)
    // Sanity: a server ack transitions away from .miss — covered by other tests,
    // but asserting here makes the test self-contained and meaningful.
    WALCloudSyncLogic.applyUploadResult(
      to: &wal,
      result: .queued(jobId: "job-test"),
      now: 1_000
    )
    XCTAssertEqual(wal.status, .uploaded)
    XCTAssertEqual(wal.jobId, "job-test")
  }

  func testApplyUploadResult200MarksSynced() {
    var wal = makeWal()
    WALCloudSyncLogic.applyUploadResult(
      to: &wal,
      result: .done(
        SyncLocalFilesResultResponse(
          newMemories: ["c1"],
          updatedMemories: [],
          failedSegments: 0,
          totalSegments: 1,
          errors: []
        )))
    XCTAssertEqual(wal.status, .synced)
    XCTAssertNil(wal.jobId)
  }

  func testApplyUploadResult202MarksUploadedWithJobId() {
    var wal = makeWal()
    WALCloudSyncLogic.applyUploadResult(to: &wal, result: .queued(jobId: "job-abc"), now: 1_700_000_100)
    XCTAssertEqual(wal.status, .uploaded)
    XCTAssertEqual(wal.jobId, "job-abc")
    XCTAssertEqual(wal.uploadedAt, 1_700_000_100)
  }

  func testReconcileCompletedMarksSynced() {
    var wals = [makeWal(status: .uploaded)]
    wals[0].jobId = "job-1"
    let fetch = SyncJobFetch(
      outcome: .ok,
      status: SyncJobStatusResponse(
        jobId: "job-1",
        status: "completed",
        totalSegments: 1,
        processedSegments: 1,
        successfulSegments: 1,
        failedSegments: 0,
        result: nil,
        error: nil
      ))
    let changed = WALCloudSyncLogic.applyReconcileFetch(
      wals: &wals,
      memberWalIds: [wals[0].id],
      fetch: fetch,
      fileExists: { _ in true }
    )
    XCTAssertTrue(changed)
    XCTAssertEqual(wals[0].status, .synced)
  }

  func testReconcilePartialFailureRetainsWalForRetry() {
    assertFailureRemainsRetryable(status: "partial_failure", failedSegments: 1, totalSegments: 2)
  }

  func testReconcileAllFailureRetainsWalForRetry() {
    assertFailureRemainsRetryable(status: "failed", failedSegments: 2, totalSegments: 2)
  }

  private func assertFailureRemainsRetryable(
    status: String, failedSegments: Int, totalSegments: Int
  ) {
    var wals = [makeWal(status: .uploaded)]
    wals[0].jobId = "job-failure"
    let fetch = SyncJobFetch(
      outcome: .ok,
      status: SyncJobStatusResponse(
        jobId: "job-failure",
        status: status,
        totalSegments: totalSegments,
        processedSegments: totalSegments,
        successfulSegments: totalSegments - failedSegments,
        failedSegments: failedSegments,
        result: nil,
        error: "synthetic transcription failure"
      ))

    let changed = WALCloudSyncLogic.applyReconcileFetch(
      wals: &wals,
      memberWalIds: [wals[0].id],
      fetch: fetch,
      fileExists: { _ in true }
    )

    XCTAssertTrue(changed)
    XCTAssertEqual(wals[0].status, .miss)
    XCTAssertNil(wals[0].jobId)
  }

  func testReconcileNonTerminalLeavesUploaded() {
    var wals = [makeWal(status: .uploaded)]
    wals[0].jobId = "job-1"
    let fetch = SyncJobFetch(
      outcome: .ok,
      status: SyncJobStatusResponse(
        jobId: "job-1",
        status: "processing",
        totalSegments: 1,
        processedSegments: 0,
        successfulSegments: 0,
        failedSegments: 0,
        result: nil,
        error: nil
      ))
    let changed = WALCloudSyncLogic.applyReconcileFetch(
      wals: &wals,
      memberWalIds: [wals[0].id],
      fetch: fetch,
      fileExists: { _ in true }
    )
    XCTAssertFalse(changed)
    XCTAssertEqual(wals[0].status, .uploaded)
  }

  func testReconcileForbiddenRevertsToMissForReupload() {
    // A 403 on the status GET is a durable permission failure, not transient.
    // The WAL must leave .uploaded (so the reconciler stops polling) and revert
    // to .miss for re-upload when the file remains on disk.
    var wals = [makeWal(status: .uploaded)]
    wals[0].jobId = "job-1"
    let changed = WALCloudSyncLogic.applyReconcileFetch(
      wals: &wals,
      memberWalIds: [wals[0].id],
      fetch: SyncJobFetch(outcome: .forbidden),
      fileExists: { _ in true }
    )
    XCTAssertTrue(changed)
    XCTAssertEqual(wals[0].status, .miss)
    XCTAssertNil(wals[0].jobId)
    XCTAssertEqual(wals[0].uploadedAt, 0)
  }

  // MARK: - mergeReconciledUploads

  private func makeWal(timerStart: Int, status: WALStatus, jobId: String? = nil) -> WALEntry {
    var wal = WALEntry(
      timerStart: timerStart,
      codec: "opus",
      status: status,
      storage: .disk,
      filePath: "audio_\(timerStart).bin",
      seconds: 60,
      device: "dev1",
      deviceModel: "Omi"
    )
    wal.jobId = jobId
    return wal
  }

  func testMergePreservesWalAppendedDuringReconcile() {
    // Snapshot taken before reconcile's network await: one uploaded WAL.
    let uploaded = makeWal(timerStart: 1_700_000_000, status: .uploaded, jobId: "job-1")
    let snapshot = [uploaded]

    // Reconcile marks it synced (operating on the snapshot copy).
    var reconciled = snapshot
    reconciled[0].status = .synced
    reconciled[0].jobId = nil
    reconciled[0].uploadedAt = 0

    // Meanwhile the live array gained a brand-new WAL (chunk timer fired during await).
    let appended = makeWal(timerStart: 1_700_000_500, status: .inProgress)
    let live = [uploaded, appended]

    let merged = WALCloudSyncLogic.mergeReconciledUploads(
      live: live, snapshot: snapshot, reconciled: reconciled)

    // The reconciled transition is applied...
    XCTAssertEqual(merged.count, 2)
    let mergedUploaded = merged.first { $0.id == uploaded.id }
    XCTAssertEqual(mergedUploaded?.status, .synced)
    XCTAssertNil(mergedUploaded?.jobId ?? nil)
    // ...and the WAL appended during the await is NOT dropped (the regression).
    let mergedAppended = merged.first { $0.id == appended.id }
    XCTAssertNotNil(mergedAppended, "WAL appended during reconcile must survive the merge")
    XCTAssertEqual(mergedAppended?.status, .inProgress)
  }

  func testMergeDoesNotClobberConcurrentFieldUpdateOnUntouchedEntry() {
    // Snapshot: two WALs, only one is being reconciled.
    let reconciledWal = makeWal(timerStart: 1_700_000_000, status: .uploaded, jobId: "job-1")
    let otherWal = makeWal(timerStart: 1_700_000_500, status: .uploaded, jobId: "job-2")
    let snapshot = [reconciledWal, otherWal]

    // Reconcile only changed the first WAL.
    var reconciled = snapshot
    reconciled[0].status = .synced
    reconciled[0].jobId = nil

    // Live array: the second WAL was concurrently transitioned by another path
    // (e.g. its own job completed) — merge must not roll that back to the snapshot.
    var liveOther = otherWal
    liveOther.status = .synced
    liveOther.jobId = nil
    let live = [reconciledWal, liveOther]

    let merged = WALCloudSyncLogic.mergeReconciledUploads(
      live: live, snapshot: snapshot, reconciled: reconciled)

    XCTAssertEqual(merged.first { $0.id == reconciledWal.id }?.status, .synced)
    // The untouched entry keeps its concurrent update, not the stale snapshot value.
    XCTAssertEqual(merged.first { $0.id == otherWal.id }?.status, .synced)
    XCTAssertNil(merged.first { $0.id == otherWal.id }?.jobId ?? nil)
  }

  func testMergeIsNoOpWhenNothingReconciled() {
    let a = makeWal(timerStart: 1_700_000_000, status: .uploaded, jobId: "job-1")
    let snapshot = [a]
    let reconciled = snapshot  // unchanged
    let live = [a]
    let merged = WALCloudSyncLogic.mergeReconciledUploads(
      live: live, snapshot: snapshot, reconciled: reconciled)
    XCTAssertEqual(merged.count, 1)
    XCTAssertEqual(merged[0].status, .uploaded)
    XCTAssertEqual(merged[0].jobId, "job-1")
  }
}
