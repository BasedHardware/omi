import Foundation
import XCTest

@testable import Omi_Computer

final class MeetingScreenshotsTests: XCTestCase {
  func testFeatureRequiresBothLocalBundleAndExplicitOverride() {
    XCTAssertFalse(
      MeetingNoteScreenshotsFeature.isEnabled(
        allowsLocalAutomation: false,
        localOverrideValue: nil))
    XCTAssertFalse(
      MeetingNoteScreenshotsFeature.isEnabled(
        allowsLocalAutomation: true,
        localOverrideValue: nil))
    XCTAssertFalse(
      MeetingNoteScreenshotsFeature.isEnabled(
        allowsLocalAutomation: true,
        localOverrideValue: "0"))
    XCTAssertTrue(
      MeetingNoteScreenshotsFeature.isEnabled(
        allowsLocalAutomation: true,
        localOverrideValue: "1"))
    XCTAssertFalse(
      MeetingNoteScreenshotsFeature.isEnabled(
        allowsLocalAutomation: false,
        localOverrideValue: "1"),
      "a shipped or external-preview bundle must stay dark even with a contaminated environment")
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
      title: "Dark launch",
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

  func testJudgeCapsPublishesInCaptureOrderAndDropsTrimmedBanner() {
    let ids = (1...8).map(Int64.init)
    let result = MeetingFrameJudge.enforce(
      rawVerdicts: ids.reversed().map { verdict(id: $0) },
      rawBanner: 8,
      sentIDs: Set(ids),
      order: ids)

    XCTAssertEqual(result.modelPublishedCount, 8)
    XCTAssertEqual(result.published.map(\.frameID), Array(ids.prefix(MeetingFrameJudge.publishCap)))
    XCTAssertNil(result.bannerFrameID)
    XCTAssertTrue(result.corrections.contains { $0.contains("over the cap") })
    XCTAssertTrue(result.corrections.contains { $0.contains("banner") })
  }

  func testJudgeSensitivityVetoesPublication() {
    let result = MeetingFrameJudge.enforce(
      rawVerdicts: [
        verdict(id: 1, sensitivity: "sensitive"),
        verdict(id: 2),
      ],
      rawBanner: 1,
      sentIDs: [1, 2],
      order: [1, 2])

    XCTAssertEqual(result.published.map(\.frameID), [2])
    XCTAssertNil(result.bannerFrameID)
    XCTAssertTrue(result.corrections.contains { $0.contains("vetoed 1") })
  }

  func testJudgeRejectsUnknownAndDuplicateFrameIDs() {
    let result = MeetingFrameJudge.enforce(
      rawVerdicts: [verdict(id: 99), verdict(id: 1), verdict(id: 1)],
      rawBanner: 1,
      sentIDs: [1],
      order: [1, 1])

    XCTAssertEqual(result.published.map(\.frameID), [1])
    XCTAssertEqual(result.bannerFrameID, 1)
    XCTAssertTrue(result.corrections.contains { $0.contains("never sent") })
    XCTAssertTrue(result.corrections.contains { $0.contains("duplicate") })
  }

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

  private func verdict(
    id: Int64,
    decision: String = "publish",
    sensitivity: String = "clean"
  ) -> [String: Any] {
    [
      "id": NSNumber(value: id),
      "decision": decision,
      "sensitivity": sensitivity,
      "caption": "Frame \(id)",
      "labels": ["meeting"],
      "reason": "useful",
    ]
  }
}
