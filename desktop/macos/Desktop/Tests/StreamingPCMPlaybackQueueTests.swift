import XCTest
@testable import Omi_Computer

final class StreamingPCMPlaybackQueueTests: XCTestCase {
  private final class BufferBox {}

  func testConfigurationChangeReturnsScheduledTailForReplay() {
    let queue = StreamingPCMPlaybackQueue<BufferBox>()
    let first = BufferBox()
    let second = BufferBox()

    queue.appendScheduled(first)
    queue.appendScheduled(second)

    let replay = queue.buffersToReplayAfterConfigurationChange()

    XCTAssertTrue(replay[0] === first)
    XCTAssertTrue(replay[1] === second)
    XCTAssertTrue(queue.isEmpty)
  }

  func testReplayedBuffersUseNewGenerationSoStaleCompletionsCannotDropThem() {
    let queue = StreamingPCMPlaybackQueue<BufferBox>()
    let buffer = BufferBox()

    let oldGeneration = queue.appendScheduled(buffer)
    _ = queue.buffersToReplayAfterConfigurationChange()
    let newGeneration = queue.appendScheduled(buffer)

    queue.markPlayed(buffer, generation: oldGeneration)
    XCTAssertFalse(
      queue.isEmpty,
      "A completion from the pre-rebuild player must not remove the replayed buffer"
    )

    queue.markPlayed(buffer, generation: newGeneration)
    XCTAssertTrue(queue.isEmpty)
  }

  func testExplicitStopClearsScheduledBuffersAndInvalidatesCompletions() {
    let queue = StreamingPCMPlaybackQueue<BufferBox>()
    let buffer = BufferBox()

    let oldGeneration = queue.appendScheduled(buffer)
    queue.clearForExplicitStop()

    XCTAssertTrue(queue.isEmpty)

    queue.appendScheduled(buffer)
    queue.markPlayed(buffer, generation: oldGeneration)

    XCTAssertFalse(
      queue.isEmpty,
      "A completion from before explicit stop must not mutate the next playback generation"
    )
  }

  func testPlayedBufferIsRemovedWithoutAffectingLaterScheduledBuffers() {
    let queue = StreamingPCMPlaybackQueue<BufferBox>()
    let first = BufferBox()
    let second = BufferBox()

    let generation = queue.appendScheduled(first)
    queue.appendScheduled(second)

    queue.markPlayed(first, generation: generation)

    XCTAssertEqual(queue.scheduledBuffers.count, 1)
    XCTAssertTrue(queue.scheduledBuffers[0] === second)
  }
}
