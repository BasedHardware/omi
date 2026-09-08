import XCTest

/// Guards parity between BLE and WiFi SD-card sync: both paths must upload
/// downloaded WALs via syncToCloud() after persisting downloaded frames.
final class SdCardSyncParityTests: XCTestCase {

  private func walSourcesRoot() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/WAL")
  }

  private func storageSyncSource() throws -> String {
    try String(
      contentsOf: walSourcesRoot().appendingPathComponent("StorageSyncService.swift"))
  }

  private func wifiSyncSource() throws -> String {
    try String(contentsOf: walSourcesRoot().appendingPathComponent("WifiSyncService.swift"))
  }

  private func finishSyncBody(from source: String) throws -> String {
    guard let start = source.range(of: "func finishSync()") else {
      throw XCTSkip("finishSync() not found")
    }
    let tail = source[start.lowerBound...]
    guard let openBrace = tail.firstIndex(of: "{") else {
      XCTFail("finishSync opening brace not found")
      return ""
    }

    var depth = 0
    var index = openBrace
    while index < tail.endIndex {
      let char = tail[index]
      if char == "{" {
        depth += 1
      } else if char == "}" {
        depth -= 1
        if depth == 0 {
          return String(tail[openBrace...index])
        }
      }
      index = tail.index(after: index)
    }

    XCTFail("finishSync body not closed")
    return ""
  }

  private func assertSyncToCloudAfterDownload(
    in source: String,
    uploadCall: String,
    file: StaticString
  ) throws {
    let body = try finishSyncBody(from: source)

    XCTAssertTrue(
      body.contains("updateWalWithDownloadedData"),
      "finishSync must persist downloaded frames before upload (\(file))")
    XCTAssertTrue(
      body.contains(uploadCall),
      "finishSync must upload WALs to cloud after download (\(file))")

    guard let update = body.range(of: "updateWalWithDownloadedData"),
      let upload = body.range(of: uploadCall)
    else {
      XCTFail("Could not locate updateWalWithDownloadedData or syncToCloud in finishSync (\(file))")
      return
    }

    XCTAssertLessThan(
      update.upperBound, upload.lowerBound,
      "syncToCloud must run after updateWalWithDownloadedData (\(file))")
  }

  private func assertSyncToCloudBeforeTeardown(
    in source: String,
    uploadCall: String,
    file: StaticString
  ) throws {
    let body = try finishSyncBody(from: source)

    guard let upload = body.range(of: uploadCall) else {
      XCTFail("Could not locate syncToCloud in finishSync (\(file))")
      return
    }

    let teardownMarker =
      body.range(of: "await cleanup()")
      ?? body.range(of: "isSyncing = false")
    guard let teardown = teardownMarker else {
      XCTFail("finishSync must reset sync state after upload (\(file))")
      return
    }

    XCTAssertLessThan(
      upload.upperBound, teardown.lowerBound,
      "syncToCloud must run before sync teardown (\(file))")
  }

  private func assertSyncToCloudAfterTeardown(
    in source: String,
    uploadCall: String,
    file: StaticString
  ) throws {
    let body = try finishSyncBody(from: source)

    guard let upload = body.range(of: uploadCall),
      let teardown = body.range(of: "await cleanup()")
    else {
      XCTFail("Could not locate syncToCloud or cleanup in finishSync (\(file))")
      return
    }

    XCTAssertLessThan(
      teardown.upperBound, upload.lowerBound,
      "WiFi sync must tear down the device SoftAP before cloud upload so internet is restored (\(file))")
  }

  func testStorageSyncFinishSyncUploadsAfterDownload() throws {
    try assertSyncToCloudAfterDownload(
      in: try storageSyncSource(),
      uploadCall: "await walService.syncToCloud()",
      file: "StorageSyncService.swift")
    try assertSyncToCloudBeforeTeardown(
      in: try storageSyncSource(),
      uploadCall: "await walService.syncToCloud()",
      file: "StorageSyncService.swift")
  }

  func testWifiSyncFinishSyncUploadsAfterDownload() throws {
    try assertSyncToCloudAfterDownload(
      in: try wifiSyncSource(),
      uploadCall: "await activeWalService.syncToCloud()",
      file: "WifiSyncService.swift")
    try assertSyncToCloudAfterTeardown(
      in: try wifiSyncSource(),
      uploadCall: "await activeWalService.syncToCloud()",
      file: "WifiSyncService.swift")
  }
}
