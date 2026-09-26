import XCTest

@testable import Omi_Computer

/// The loader is the one door from the Rewind store to chat surfaces, so its
/// exclusion filter *is* the privacy guarantee: capture-time exclusion is not
/// retroactive, and pre-exclusion password-manager rows persist in the store.
/// Every test here runs against an injected fake store — no GRDB, no files.
@MainActor
final class RewindFrameLoaderTests: XCTestCase {
  private let omiJPEG = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10])

  private func row(
    id: Int64,
    appName: String,
    ageSeconds: TimeInterval = 10,
    videoChunkPath: String? = nil,
    frameOffset: Int? = nil
  ) -> Screenshot {
    Screenshot(
      id: id,
      timestamp: Date().addingTimeInterval(-ageSeconds),
      appName: appName,
      windowTitle: "\(appName) window",
      videoChunkPath: videoChunkPath,
      frameOffset: frameOffset
    )
  }

  private func loader(
    rows: [Screenshot],
    excludedApps: Set<String> = [],
    activeChunk: String? = nil,
    loadErrorRowIDs: Set<Int64> = [],
    loadedData: Data? = nil
  ) -> RewindFrameLoader {
    // A local, not `self.omiJPEG`: the environment's closures are @Sendable
    // and must not capture the non-Sendable test case.
    let fallbackData = loadedData ?? omiJPEG
    let environment = RewindFrameLoader.Environment(
      recentScreenshots: { limit in Array(rows.prefix(limit)) },
      activeChunkPath: { activeChunk },
      loadData: { screenshot in
        if let id = screenshot.id, loadErrorRowIDs.contains(id) {
          throw RewindError.screenshotNotFound
        }
        return fallbackData
      },
      excludedApps: { excludedApps }
    )
    return RewindFrameLoader(environment: environment)
  }

  func testExcludedAppRowsNeverSurfaceEvenWhenPresentInTheStore() async {
    // The whole privacy contract: exclusion at capture is forward-looking
    // only, so the read must refuse rows the user has since excluded.
    let loader = loader(
      rows: [
        row(id: 1, appName: "1Password", ageSeconds: 5),
        row(id: 2, appName: "ChatGPT", ageSeconds: 20),
      ],
      excludedApps: ["1Password"]
    )
    let frames = await loader.attachableRows(limit: 25)
    XCTAssertEqual(frames.map(\.appName), ["ChatGPT"])
    let latest = await loader.latestAttachableRow()
    XCTAssertEqual(latest?.appName, "ChatGPT")
  }

  func testOmiRowsAreFilteredUnconditionally() async {
    // A frame of Omi describing itself is the defect this loader exists to
    // prevent, so the Omi names are filtered even when the user-editable
    // exclusion list does not contain them.
    let loader = loader(
      rows: [
        row(id: 1, appName: "Omi", ageSeconds: 5),
        row(id: 2, appName: "Omi Beta", ageSeconds: 6),
        row(id: 3, appName: "Safari", ageSeconds: 30),
      ],
      excludedApps: []
    )
    let frames = await loader.attachableRows(limit: 25)
    XCTAssertEqual(frames.map(\.appName), ["Safari"])
  }

  func testActiveChunkRowsAreSkippedWithoutDecoding() async {
    // The chunk still being written cannot be decoded mid-write; the row is
    // skipped before any load is attempted, and the next older row wins.
    let loader = loader(
      rows: [
        row(id: 1, appName: "ChatGPT", ageSeconds: 2, videoChunkPath: "chunk-9", frameOffset: 3),
        row(id: 2, appName: "Safari", ageSeconds: 40, videoChunkPath: "chunk-8", frameOffset: 1),
      ],
      activeChunk: "chunk-9"
    )
    let frames = await loader.attachableRows(limit: 25)
    XCTAssertEqual(frames.map(\.appName), ["Safari"])
  }

  func testUnreadableRowFallsThroughToTheNextOlderOne() async {
    let loader = loader(
      rows: [
        row(id: 1, appName: "ChatGPT", ageSeconds: 5),
        row(id: 2, appName: "Safari", ageSeconds: 30),
      ],
      loadErrorRowIDs: [1]
    )
    let frame = await loader.loadLatestAttachableFrame()
    XCTAssertEqual(frame?.appName, "Safari")
  }

  func testLoadDataRejectsARowExcludedWhileTheDecodeRan() async {
    // The picker resolved the row when it was attachable; the user then
    // excluded its app. The bytes that come back must not ship. The exclusion
    // flips between the pick (attachableRows) and the load (loadData), which
    // is exactly the suspended-decode window the revalidation covers.
    final class Exclusions: @unchecked Sendable {
      let lock = NSLock()
      private var apps: Set<String> = []
      func set(_ apps: Set<String>) { lock.withLock { self.apps = apps } }
      func get() -> Set<String> { lock.withLock { apps } }
    }
    let exclusions = Exclusions()
    // Locals, not self members: the environment's closures are @Sendable and
    // must not capture the non-Sendable test case.
    let jpeg = omiJPEG
    let pickedRow = row(id: 5, appName: "1Password", ageSeconds: 5)
    let environment = RewindFrameLoader.Environment(
      recentScreenshots: { _ in [pickedRow] },
      activeChunkPath: { nil },
      loadData: { _ in jpeg },
      excludedApps: { exclusions.get() }
    )
    let loader = RewindFrameLoader(environment: environment)
    let picked = await loader.attachableRows(limit: 25)
    XCTAssertEqual(picked.map(\.appName), ["1Password"], "precondition: row was attachable at pick time")
    exclusions.set(["1Password"])
    let data = await loader.loadData(for: picked[0])
    XCTAssertNil(data)
  }

  func testLoadDataRejectsARowWhoseChunkBecameActiveWhileTheDecodeRan() async {
    final class ActiveChunk: @unchecked Sendable {
      let lock = NSLock()
      private var path: String?
      func set(_ path: String?) { lock.withLock { self.path = path } }
      func get() -> String? { lock.withLock { path } }
    }
    let activeChunk = ActiveChunk()
    let jpeg = omiJPEG
    let theRow = row(id: 6, appName: "ChatGPT", ageSeconds: 5, videoChunkPath: "chunk-1", frameOffset: 2)
    let environment = RewindFrameLoader.Environment(
      recentScreenshots: { _ in [theRow] },
      activeChunkPath: { activeChunk.get() },
      loadData: { _ in jpeg },
      excludedApps: { [] }
    )
    let loader = RewindFrameLoader(environment: environment)
    let picked = await loader.attachableRows(limit: 25)
    XCTAssertEqual(picked.count, 1, "precondition: row was attachable before its chunk went active")
    activeChunk.set("chunk-1")
    let data = await loader.loadData(for: picked[0])
    XCTAssertNil(data)
  }

  func testAgeBoundStopsTheSearchAtTheNewestRow() async {
    // Rows are newest-first, so the first row past the bound ends the search —
    // there is nothing younger left to find.
    let loader = loader(
      rows: [
        row(id: 1, appName: "ChatGPT", ageSeconds: 500),
        row(id: 2, appName: "Safari", ageSeconds: 900),
      ]
    )
    let frame = await loader.loadLatestAttachableFrame(
      maxAgeSeconds: ScreenContextFallbackPolicy.maxFallbackFrameAgeSeconds
    )
    XCTAssertNil(frame)
  }

  func testLoadDataForRowIDResolvesThePickedRow() async {
    let loader = loader(
      rows: [
        row(id: 7, appName: "ChatGPT", ageSeconds: 15),
        row(id: 8, appName: "Safari", ageSeconds: 60),
      ]
    )
    let data = await loader.loadData(forRowID: 8)
    XCTAssertEqual(data, omiJPEG)
    let missing = await loader.loadData(forRowID: 999)
    XCTAssertNil(missing)
  }

  func testStagingWritesATempJPEGTheAttachmentCanRead() throws {
    let unwrapped = try XCTUnwrap(
      RecentScreenFrameStaging.attachment(
        appName: "ChatGPT",
        jpegData: omiJPEG,
        capturedAt: Date()
      ))
    let url = try XCTUnwrap(unwrapped.localFileURL)
    defer { try? FileManager.default.removeItem(at: url) }
    XCTAssertTrue(unwrapped.isImage)
    XCTAssertEqual(unwrapped.mimeType, "image/jpeg")
    XCTAssertEqual(try Data(contentsOf: url), omiJPEG)
  }

  func testStagingSanitizesAppNameIntoTheFileName() throws {
    let attachment = RecentScreenFrameStaging.attachment(
      appName: "Code/Editor: Pro",
      jpegData: omiJPEG,
      capturedAt: Date()
    )
    let url = try XCTUnwrap(attachment?.localFileURL)
    defer { try? FileManager.default.removeItem(at: url) }
    XCTAssertTrue(url.lastPathComponent.contains("Code-Editor- Pro"))
    // Directory traversal: an unsanitized appName would create a nested
    // directory instead of a file directly inside the frames directory.
    XCTAssertEqual(
      url.deletingLastPathComponent().standardizedFileURL.path,
      RecentScreenFrameStaging.framesDirectoryForTesting.standardizedFileURL.path)
    // App-owned: staged frames are cleaned up by the attachment lifecycle.
    XCTAssertEqual(attachment?.appOwnedFileURL, url)
  }

  func testAwaitSummonBoundaryReturnsABoundaryRecordedAfterTheCutoff() async {
    let loader = loader(rows: [])
    let cutoff = Date()
    loader.storeSummonBoundary(
      LoadedRewindFrame(data: omiJPEG, appName: "ChatGPT", windowTitle: nil, timestamp: cutoff.addingTimeInterval(0.05))
    )
    let frame = await loader.awaitSummonBoundary(
      recordedAfter: cutoff, timeoutNanoseconds: 100_000_000)
    XCTAssertEqual(frame?.appName, "ChatGPT")
  }

  func testAwaitSummonBoundaryNeverReturnsAnOlderSummon() async {
    // A boundary from an earlier summon must not pass itself off as this
    // tap's referent: an expired wait falls back to nil so the caller uses
    // the store-frame fallback, whose loader excludes Omi.
    let loader = loader(rows: [])
    let cutoff = Date()
    loader.storeSummonBoundary(
      LoadedRewindFrame(
        data: omiJPEG, appName: "ChatGPT", windowTitle: nil,
        timestamp: cutoff.addingTimeInterval(-60))
    )
    let frame = await loader.awaitSummonBoundary(
      recordedAfter: cutoff, timeoutNanoseconds: 60_000_000)
    XCTAssertNil(frame)
  }
}
