import AVFoundation
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

  func testConfigurationChangeReplayPreservesTailOrder() {
    let queue = StreamingPCMPlaybackQueue<BufferBox>()
    let first = BufferBox()
    let second = BufferBox()

    queue.appendScheduled(first)
    queue.appendScheduled(second)
    let replay = queue.buffersToReplayAfterConfigurationChange()
    for buffer in replay {
      queue.appendScheduled(buffer)
    }

    XCTAssertEqual(queue.scheduledBuffers.count, 2)
    XCTAssertTrue(queue.scheduledBuffers[0] === first)
    XCTAssertTrue(queue.scheduledBuffers[1] === second)
  }

  func testReplayedBuffersUseNewGenerationSoStaleCompletionsCannotDropThem() {
    let queue = StreamingPCMPlaybackQueue<BufferBox>()
    let buffer = BufferBox()

    let oldGeneration = queue.appendScheduled(buffer)
    _ = queue.buffersToReplayAfterConfigurationChange()
    let newGeneration = queue.appendScheduled(buffer)

    XCTAssertFalse(queue.markPlayed(buffer, generation: oldGeneration))
    XCTAssertFalse(
      queue.isEmpty,
      "A completion from the pre-rebuild player must not remove the replayed buffer"
    )

    XCTAssertTrue(queue.markPlayed(buffer, generation: newGeneration))
    XCTAssertTrue(queue.isEmpty)
  }

  func testExplicitStopClearsScheduledBuffersAndInvalidatesCompletions() {
    let queue = StreamingPCMPlaybackQueue<BufferBox>()
    let buffer = BufferBox()

    let oldGeneration = queue.appendScheduled(buffer)
    queue.clearForExplicitStop()

    XCTAssertTrue(queue.isEmpty)

    queue.appendScheduled(buffer)
    XCTAssertFalse(queue.markPlayed(buffer, generation: oldGeneration))

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

    XCTAssertTrue(queue.markPlayed(first, generation: generation))

    XCTAssertEqual(queue.scheduledBuffers.count, 1)
    XCTAssertTrue(queue.scheduledBuffers[0] === second)
  }

  func testConfigurationRecoveryDefersAndCoalescesNotificationWork() {
    let pendingActions = PendingRecoveryActions()
    let recovery = DeferredConfigurationRecovery(onMainQueue: pendingActions.schedule)
    var recoveryCount = 0

    recovery.schedule {
      recoveryCount += 1
      recovery.schedule { recoveryCount += 1 }
    }
    recovery.schedule { recoveryCount += 1 }

    XCTAssertEqual(recoveryCount, 0)
    XCTAssertEqual(pendingActions.count, 1)

    pendingActions.runFirst()

    XCTAssertEqual(recoveryCount, 1)
    XCTAssertEqual(pendingActions.count, 0)

    recovery.schedule { recoveryCount += 1 }

    XCTAssertEqual(pendingActions.count, 1)
    pendingActions.runFirst()
    XCTAssertEqual(recoveryCount, 2)
  }

  func testConfigurationRecoveryCancellationDiscardsPendingWork() {
    let pendingActions = PendingRecoveryActions()
    let recovery = DeferredConfigurationRecovery(onMainQueue: pendingActions.schedule)
    var recoveryCount = 0

    recovery.schedule { recoveryCount += 1 }
    recovery.cancel()
    pendingActions.runFirst()

    XCTAssertEqual(recoveryCount, 0)

    recovery.schedule { recoveryCount += 1 }
    pendingActions.runFirst()

    XCTAssertEqual(recoveryCount, 1)
  }
}

private final class PendingRecoveryActions: @unchecked Sendable {
  private let lock = NSLock()
  private var actions: [@Sendable () -> Void] = []

  var count: Int {
    lock.lock()
    defer { lock.unlock() }
    return actions.count
  }

  func schedule(_ action: @escaping @Sendable () -> Void) {
    lock.lock()
    actions.append(action)
    lock.unlock()
  }

  func runFirst() {
    lock.lock()
    let action = actions.removeFirst()
    lock.unlock()
    action()
  }
}

final class StreamingPCMPlayerLevelTests: XCTestCase {
  func testRmsLevelMeasuresSignalAndBoundsToOne() throws {
    let format = try XCTUnwrap(
      AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 24000, channels: 1, interleaved: false))
    let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 256))
    buffer.frameLength = 256
    let channel = try XCTUnwrap(buffer.floatChannelData)[0]

    for i in 0..<256 { channel[i] = 0 }
    XCTAssertEqual(StreamingPCMPlayer.rmsLevel(of: buffer), 0, accuracy: 0.001)

    for i in 0..<256 { channel[i] = 0.5 }
    XCTAssertEqual(StreamingPCMPlayer.rmsLevel(of: buffer), 0.5, accuracy: 0.01)

    for i in 0..<256 { channel[i] = i % 2 == 0 ? 2.0 : -2.0 }
    XCTAssertEqual(StreamingPCMPlayer.rmsLevel(of: buffer), 1, accuracy: 0.001)

    buffer.frameLength = 0
    XCTAssertEqual(StreamingPCMPlayer.rmsLevel(of: buffer), 0, accuracy: 0.001)
  }
}
