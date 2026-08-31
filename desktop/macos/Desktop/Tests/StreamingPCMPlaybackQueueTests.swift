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

  func testPhysicalCompletionsReportProgressForEachBufferAndIdleOnlyAtTheEnd() {
    let queue = StreamingPCMPlaybackQueue<BufferBox>()
    let first = BufferBox()
    let second = BufferBox()
    let third = BufferBox()
    let generation = queue.appendScheduled(first)
    queue.appendScheduled(second)
    queue.appendScheduled(third)

    let firstCompletion = queue.markPlayedResult(first, generation: generation)
    let secondCompletion = queue.markPlayedResult(second, generation: generation)
    let finalCompletion = queue.markPlayedResult(third, generation: generation)

    XCTAssertEqual(
      [
        firstCompletion?.remainingBufferCount, secondCompletion?.remainingBufferCount,
        finalCompletion?.remainingBufferCount,
      ],
      [2, 1, 0])
    XCTAssertEqual(
      [firstCompletion?.isIdle, secondCompletion?.isIdle, finalCompletion?.isIdle],
      [false, false, true])
    XCTAssertEqual(finalCompletion?.generation, generation)
    XCTAssertTrue(queue.isEmpty)
  }

  func testStaleReplayCompletionProducesNoProgressResult() {
    let queue = StreamingPCMPlaybackQueue<BufferBox>()
    let buffer = BufferBox()

    let oldGeneration = queue.appendScheduled(buffer)
    _ = queue.buffersToReplayAfterConfigurationChange()
    let newGeneration = queue.appendScheduled(buffer)

    XCTAssertNil(queue.markPlayedResult(buffer, generation: oldGeneration))
    XCTAssertEqual(queue.scheduledBufferCount, 1)
    XCTAssertNotNil(queue.markPlayedResult(buffer, generation: newGeneration))
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
    XCTAssertNil(queue.markPlayedResult(buffer, generation: oldGeneration))
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
  func testRenderCapacityRaisesRouteChanged480FrameNodeAbove512FrameDeviceSlice() {
    let engine = AVAudioEngine()
    let player = AVAudioPlayerNode()
    engine.attach(player)
    engine.connect(player, to: engine.mainMixerNode, format: nil)
    player.auAudioUnit.maximumFramesToRender = 480
    engine.mainMixerNode.auAudioUnit.maximumFramesToRender = 480

    let capacities = StreamingPCMRenderCapacity.configure(
      units: [player.auAudioUnit, engine.mainMixerNode.auAudioUnit])

    XCTAssertEqual(capacities, [4096, 4096])
    XCTAssertGreaterThanOrEqual(player.auAudioUnit.maximumFramesToRender, 512)
    XCTAssertGreaterThanOrEqual(engine.mainMixerNode.auAudioUnit.maximumFramesToRender, 512)
  }

  func testStreamingPlayerConfiguresSafeRenderCapacityBeforePlaybackStarts() {
    let player = StreamingPCMPlayer(sampleRate: 24000)
    defer { player.stop() }

    XCTAssertEqual(player.renderCapacities, [4096, 4096])
  }

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

@MainActor
final class RealtimeHubPlaybackProgressBridgeTests: XCTestCase {
  func testPhysicalPlayerProgressRefreshesOnlyTheCurrentNativeLease() async throws {
    let defaults = UserDefaults.standard
    let previousAuthOwner = defaults.object(forKey: .authUserId)
    let previousAutomationOwner = defaults.object(forKey: .automationOwnerOverride)
    defaults.set("ptt-playback-bridge-owner", forKey: .authUserId)
    defaults.removeObject(forKey: .automationOwnerOverride)
    defer {
      if let previousAuthOwner {
        defaults.set(previousAuthOwner, forKey: .authUserId)
      } else {
        defaults.removeObject(forKey: .authUserId)
      }
      if let previousAutomationOwner {
        defaults.set(previousAutomationOwner, forKey: .automationOwnerOverride)
      } else {
        defaults.removeObject(forKey: .automationOwnerOverride)
      }
    }
    let coordinator = VoiceTurnCoordinator.shared
    coordinator.reset()
    defer { coordinator.reset() }
    let turnID = RealtimeAutomationTurnHarness.begin(on: coordinator)
    coordinator.publish(.selectRoute(turnID: turnID, route: .deepgramBatch))
    coordinator.publish(.finalize(turnID: turnID))
    coordinator.publish(.transcriptionStarted(turnID: turnID))
    coordinator.publish(.transcriptionFinal(turnID: turnID, text: "fixture"))
    guard case .acquired = coordinator.acquireOutput(.nativeRealtime, turnID: turnID) else {
      return XCTFail("expected native realtime output lease")
    }

    let controller = RealtimeHubController()
    let player = controller.makePCMPlayer()
    controller.pcmPlayer = player
    let initialProgressCount = coordinator.timelineSnapshot().filter {
      $0.event == "playback_progress_scoped"
    }.count

    player.onPlaybackProgress?(
      StreamingPCMPlaybackProgress(
        playbackEpoch: 1,
        queueGeneration: player.playbackQueueGeneration,
        remainingBufferCount: 2))
    await Task.yield()

    XCTAssertEqual(
      coordinator.timelineSnapshot().filter { $0.event == "playback_progress_scoped" }.count,
      initialProgressCount + 1)

    player.onPlaybackProgress?(
      StreamingPCMPlaybackProgress(
        playbackEpoch: 2,
        queueGeneration: player.playbackQueueGeneration + 1,
        remainingBufferCount: 1))
    await Task.yield()

    XCTAssertEqual(
      coordinator.timelineSnapshot().filter { $0.event == "playback_progress_scoped" }.count,
      initialProgressCount + 1,
      "a stale playback generation must not refresh the active turn")

    let replacement = StreamingPCMPlayer(sampleRate: 24000)
    controller.pcmPlayer = replacement
    player.onPlaybackProgress?(
      StreamingPCMPlaybackProgress(
        playbackEpoch: 3,
        queueGeneration: player.playbackQueueGeneration,
        remainingBufferCount: 0))
    await Task.yield()

    XCTAssertEqual(
      coordinator.timelineSnapshot().filter { $0.event == "playback_progress_scoped" }.count,
      initialProgressCount + 1,
      "a replaced player must not refresh the active turn")
    player.stop()
    replacement.stop()
  }
}
