import CryptoKit
import Foundation
import XCTest

@testable import Omi_Computer

#if canImport(AppKit)
  import AppKit
#endif

final class MeetingScreenshotsTests: XCTestCase {
  func testFeatureDefaultsOnAndRespectsExplicitOverride() {
    XCTAssertTrue(
      MeetingNoteScreenshotsFeature.isEnabled(storedValue: nil),
      "absent local mirror must read as on, matching the contract's default")
    XCTAssertTrue(MeetingNoteScreenshotsFeature.isEnabled(storedValue: true))
    XCTAssertFalse(MeetingNoteScreenshotsFeature.isEnabled(storedValue: false))
  }

  @MainActor
  func testDisabledStoreStopsBeforeCandidateSelection() {
    var didSelect = false
    let store = MeetingScreenshotsStore(
      featureEnabled: { false },
      selectCandidates: { _, _ in
        didSelect = true
        return MeetingFrameSelector.Outcome()
      })

    store.load(
      conversationID: "conversation",
      start: Date(timeIntervalSince1970: 100),
      end: Date(timeIntervalSince1970: 200))

    XCTAssertEqual(store.phase, .disabled)
    XCTAssertFalse(didSelect, "the disabled path must not touch Rewind or start adjudication")
  }

  func testSelectorWindowIsInclusiveAndRejectsInvalidWindows() async {
    let start = Date(timeIntervalSince1970: 1_000)
    let end = start.addingTimeInterval(600)
    let frames = [
      candidate(id: 1, timestamp: start.addingTimeInterval(-1), windowTitle: "before"),
      candidate(id: 2, timestamp: start, windowTitle: "start"),
      candidate(id: 3, timestamp: end, windowTitle: "end"),
      candidate(id: 4, timestamp: end.addingTimeInterval(1), windowTitle: "after"),
    ]

    let outcome = await MeetingFrameSelector.selectCandidates(
      frames,
      from: start,
      to: end,
      perceptualHash: { _ in nil })
    XCTAssertEqual(outcome.framesInWindow, 2)
    XCTAssertEqual(outcome.candidates.map(\.id), [2, 3])

    let invalid = await MeetingFrameSelector.selectCandidates(
      frames,
      from: end,
      to: start,
      perceptualHash: { _ in nil })
    XCTAssertEqual(invalid.framesInWindow, 0)
    XCTAssertTrue(invalid.candidates.isEmpty)
  }

  func testSelectorAppliesAppAndWindowTitleDenylistBeforeCompaction() async {
    let start = Date(timeIntervalSince1970: 2_000)
    let frames = [
      candidate(id: 1, timestamp: start, appName: "Slack", windowTitle: "Team chat"),
      candidate(id: 2, timestamp: start, appName: "Xcode", windowTitle: "Rotate API Key"),
      candidate(id: 3, timestamp: start, appName: "Safari", windowTitle: "Project plan"),
    ]

    let outcome = await MeetingFrameSelector.selectCandidates(
      frames,
      from: start,
      to: start.addingTimeInterval(60),
      perceptualHash: { _ in nil })

    XCTAssertEqual(outcome.framesInWindow, 3)
    XCTAssertEqual(outcome.candidates.map(\.id), [3])
    XCTAssertEqual(outcome.drops["denylisted"], 2)
  }

  func testSelectorBucketChoosesRichestOCRAndDropsUnusableFrames() async {
    let start = Date(timeIntervalSince1970: 3_000)
    let richText = String(repeating: "useful meeting artifact ", count: 4)
    let frames = [
      candidate(id: 1, timestamp: start, imagePath: nil, videoChunkPath: nil),
      candidate(id: 2, timestamp: start.addingTimeInterval(10), ocrText: nil),
      candidate(id: 3, timestamp: start.addingTimeInterval(20), ocrText: richText),
      candidate(
        id: 4,
        timestamp: start.addingTimeInterval(130),
        windowTitle: "Other",
        videoChunkPath: "active.mp4"),
    ]

    let outcome = await MeetingFrameSelector.selectCandidates(
      frames,
      from: start,
      to: start.addingTimeInterval(180),
      unfinalizedChunk: "active.mp4",
      perceptualHash: { _ in nil })

    XCTAssertEqual(outcome.candidates.map(\.id), [3])
    XCTAssertEqual(outcome.drops["no pixels recorded"], 1)
    XCTAssertEqual(outcome.drops["chunk still being written"], 1)
    XCTAssertEqual(outcome.drops["same window, same minutes"], 1)
  }

  func testSelectorCeilingMatchesServerMaxCandidates() async {
    // Contract §3: `max_candidates=8` for `meeting_note_v1`. The selector's ceiling is pinned to
    // the same constant so nothing needs a second trim at the upload boundary.
    XCTAssertEqual(MeetingFrameSelector.candidateCeiling, 8)
    XCTAssertEqual(MeetingFrameJudge.maxCandidatesPerRequest, 8)

    let start = Date(timeIntervalSince1970: 4_000)
    // 10 frames, each in its own bucket and app/window so none of them compact or dedup away —
    // only the ceiling should reduce this set.
    let frames = (0..<10).map { i in
      candidate(
        id: Int64(i), timestamp: start.addingTimeInterval(Double(i) * 300), appName: "App\(i)",
        windowTitle: "Window\(i)")
    }

    let outcome = await MeetingFrameSelector.selectCandidates(
      frames,
      from: start,
      to: start.addingTimeInterval(3_600),
      perceptualHash: { _ in nil })

    XCTAssertEqual(outcome.candidates.count, 8)
    XCTAssertEqual(outcome.drops["over the candidate ceiling"], 2)
  }

  func testTextAndHashSimilarityBoundaries() {
    let normalized = MeetingFrameSimilarity.shingles("One TWO, three four five six")
    XCTAssertEqual(normalized, MeetingFrameSimilarity.shingles("one two three four five six"))
    XCTAssertEqual(normalized.count, 2)
    XCTAssertEqual(MeetingFrameSimilarity.jaccard([1, 2], [2, 3]), 1.0 / 3.0, accuracy: 0.000_001)
    XCTAssertEqual(MeetingFrameSimilarity.jaccard([], [1]), 0)

    XCTAssertEqual(MeetingFrameSimilarity.similarity(0, 0), 1)
    XCTAssertEqual(MeetingFrameSimilarity.similarity(0, UInt64.max), 0)
    XCTAssertEqual(MeetingFrameSimilarity.similarity(0, 1), 63.0 / 64.0, accuracy: 0.000_001)
  }

  #if canImport(AppKit)
    func testMakeCandidateWireComputesDigestAndDimensions() throws {
      let bytes = try Self.jpegData(width: 4, height: 3)
      let timestamp = Date(timeIntervalSince1970: 5_000)

      let wire = MeetingFrameJudge.makeCandidateWire(id: 42, timestamp: timestamp, bytes: bytes)

      let expectedDigest = Data(SHA256.hash(data: bytes)).base64EncodedString()
      XCTAssertEqual(wire?.clientFrameID, "42")
      XCTAssertEqual(wire?.capturedAt, timestamp)
      XCTAssertEqual(wire?.mimeType, "image/jpeg")
      XCTAssertEqual(wire?.declaredWidth, 4)
      XCTAssertEqual(wire?.declaredHeight, 3)
      XCTAssertEqual(wire?.sha256Base64, expectedDigest)
      XCTAssertEqual(wire?.sha256Base64.count, 44, "a base64 SHA-256 digest is always 44 characters")
      XCTAssertEqual(wire?.bytesBase64, bytes.base64EncodedString())
    }

    func testMakeCandidateWireRejectsUnreadableBytes() {
      XCTAssertNil(MeetingFrameJudge.makeCandidateWire(id: 1, timestamp: Date(), bytes: Data()))
      XCTAssertNil(
        MeetingFrameJudge.makeCandidateWire(
          id: 1, timestamp: Date(), bytes: Data([0x00, 0x01, 0x02])))
    }

    func testMimeTypeSniffsPNGAndDefaultsToJPEG() throws {
      let pngData = try Self.pngData(width: 2, height: 2)
      XCTAssertEqual(MeetingFrameJudge.mimeType(of: pngData), "image/png")

      let jpegData = try Self.jpegData(width: 2, height: 2)
      XCTAssertEqual(MeetingFrameJudge.mimeType(of: jpegData), "image/jpeg")
    }

    private static func jpegData(width: Int, height: Int) throws -> Data {
      guard
        let rep = NSBitmapImageRep(
          bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8,
          samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
          bytesPerRow: 0, bitsPerPixel: 0),
        let data = rep.representation(using: .jpeg, properties: [:])
      else { throw XCTSkip("could not build a fixture JPEG on this machine") }
      return data
    }

    private static func pngData(width: Int, height: Int) throws -> Data {
      guard
        let rep = NSBitmapImageRep(
          bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8,
          samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
          bytesPerRow: 0, bitsPerPixel: 0),
        let data = rep.representation(using: .png, properties: [:])
      else { throw XCTSkip("could not build a fixture PNG on this machine") }
      return data
    }
  #endif

  private func candidate(
    id: Int64,
    timestamp: Date,
    appName: String = "Xcode",
    windowTitle: String? = "Editor",
    imagePath: String? = "frame.jpg",
    videoChunkPath: String? = nil,
    ocrText: String? = nil
  ) -> MeetingFrameCandidate {
    MeetingFrameCandidate(
      id: id,
      timestamp: timestamp,
      appName: appName,
      windowTitle: windowTitle,
      imagePath: imagePath,
      videoChunkPath: videoChunkPath,
      frameOffset: 0,
      ocrText: ocrText)
  }
}
