import XCTest
@testable import Omi_Computer
import OmiWAL

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
    var wal = makeWal()
    // Local parse alone — no applyUploadResult call — must stay miss
    XCTAssertEqual(wal.status, .miss)
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
}
