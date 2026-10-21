import XCTest

@testable import Omi_Computer

final class RewindCitationFocusTests: XCTestCase {
  @MainActor
  func testScreenshotIDParserRejectsMalformedAndNonPositiveValues() {
    XCTAssertEqual(RewindCitationFocusState.parseScreenshotID(" 42 "), 42)
    XCTAssertNil(RewindCitationFocusState.parseScreenshotID(""))
    XCTAssertNil(RewindCitationFocusState.parseScreenshotID("42x"))
    XCTAssertNil(RewindCitationFocusState.parseScreenshotID("0"))
    XCTAssertNil(RewindCitationFocusState.parseScreenshotID("-1"))
    XCTAssertNil(RewindCitationFocusState.parseScreenshotID("9223372036854775808"))
  }

  @MainActor
  func testCitationTargetIsInsertedIntoSampledTimelineInTimestampOrder() {
    let older = Screenshot(id: 1, timestamp: Date(timeIntervalSince1970: 10), appName: "Editor")
    let newer = Screenshot(id: 3, timestamp: Date(timeIntervalSince1970: 30), appName: "Editor")
    let target = Screenshot(id: 2, timestamp: Date(timeIntervalSince1970: 20), appName: "Editor")

    let result = RewindViewModel.insertingCitationTarget(target, into: [older, newer])

    XCTAssertEqual(result.map(\.id), [1, 2, 3])
    XCTAssertEqual(
      RewindViewModel.insertingCitationTarget(target, into: result).map(\.id),
      [1, 2, 3],
      "a repeated focus request must not duplicate the exact row"
    )
  }

  @MainActor
  func testCitationResolutionRejectsOwnerSwitchDuringDatabaseRead() async {
    guard let owner = RewindCaptureOwnerSnapshot.capture() else {
      return XCTFail("owner snapshot should be available for this local resolution test")
    }
    let readStarted = expectation(description: "citation row read started")
    let releaseRead = AsyncStream<Void>.makeStream()
    let screenshot = Screenshot(
      id: 42,
      timestamp: Date(timeIntervalSince1970: 42),
      appName: "Editor",
      imagePath: "frame.jpg"
    )
    let viewModel = RewindViewModel(
      timelineScreenshotLoader: { _, _, _, _ in [] },
      citationScreenshotLoader: { _ in
        readStarted.fulfill()
        for await _ in releaseRead.stream { break }
        return screenshot
      }
    )
    let request = RewindCitationFocusState.Request(screenshotID: 42, owner: owner)
    let resolutionTask = Task { await viewModel.resolveCitationRequest(request) }

    await fulfillment(of: [readStarted], timeout: 1)
    RewindCaptureOwnerGeneration.beginTransition()
    RewindCaptureOwnerGeneration.endTransition()
    releaseRead.continuation.yield(())

    let resolution = await resolutionTask.value
    XCTAssertEqual(resolution, .staleOwner)
  }

  @MainActor
  func testCitationFocusShowsUnavailableWhenRowDisappearsAfterValidation() async {
    guard let owner = RewindCaptureOwnerSnapshot.capture() else {
      return XCTFail("owner snapshot should be available for this local resolution test")
    }
    let screenshot = Screenshot(
      id: 43,
      timestamp: Date(timeIntervalSince1970: 43),
      appName: "Editor",
      imagePath: "frame.jpg",
      videoChunkPath: "chunk.mp4"
    )
    let reads = CitationReadSequence(first: screenshot)
    let viewModel = RewindViewModel(
      timelineScreenshotLoader: { _, _, _, _ in [] },
      citationScreenshotLoader: { _ in await reads.next() }
    )
    let request = RewindCitationFocusState.Request(screenshotID: 43, owner: owner)

    guard case .found(let validated) = await viewModel.resolveCitationRequest(request) else {
      return XCTFail("the click-time validation should find the seeded row")
    }
    let admission = await viewModel.focusCitationScreenshotResult(validated, ownerLease: owner)

    XCTAssertEqual(admission, RewindCitationFocusAdmission.unavailable)
    XCTAssertTrue(viewModel.screenshots.isEmpty)
    let readCount = await reads.count()
    XCTAssertEqual(readCount, 2, "focus must re-read the canonical row before insertion")
    XCTAssertEqual(
      RewindCitationUnavailablePresentationPolicy.message(for: 43),
      "Frame 43 is no longer available locally. It may have been pruned."
    )
  }

  private actor CitationReadSequence {
    private var readCount = 0
    private let first: Screenshot

    init(first: Screenshot) {
      self.first = first
    }

    func next() -> Screenshot? {
      readCount += 1
      return readCount == 1 ? first : nil
    }

    func count() -> Int { readCount }
  }
}
