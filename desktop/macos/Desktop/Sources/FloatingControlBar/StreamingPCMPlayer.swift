@preconcurrency import AVFoundation
import Foundation

/// `AVAudioPCMBuffer` is not Sendable; this box lets a scheduled-buffer
/// completion carry the buffer across to the main-actor bookkeeping hop.
private struct PCMBufferBox: @unchecked Sendable {
  let buffer: AVAudioPCMBuffer
}

/// Tracks buffers that AVAudioPlayerNode owns but has not reported as played yet.
///
/// `AVAudioPlayerNode.stop()` discards every scheduled buffer. Route/sample-rate
/// changes force us to stop and rebuild the node graph, so the app must own a
/// mirror of the scheduled tail and replay it after recovery. Keep this small
/// state machine separate from AVFoundation calls so route-change behavior is
/// testable without real audio hardware.
final class StreamingPCMPlaybackQueue<Buffer: AnyObject> {
  /// The result of accepting one physical buffer completion.
  ///
  /// A completion is emitted only when the callback belongs to the queue's
  /// current generation. The remaining count is intentionally bounded to
  /// queue metadata; it contains no audio content and is useful for liveness
  /// diagnostics and deciding whether this completion drained the tail.
  struct Completion: Equatable, Sendable {
    let generation: Int
    let remainingBufferCount: Int

    var isIdle: Bool { remainingBufferCount == 0 }
  }

  private(set) var scheduledBuffers: [Buffer] = []
  private(set) var generation = 0

  var isEmpty: Bool { scheduledBuffers.isEmpty }
  var scheduledBufferCount: Int { scheduledBuffers.count }

  @discardableResult
  func appendScheduled(_ buffer: Buffer) -> Int {
    scheduledBuffers.append(buffer)
    return generation
  }

  @discardableResult
  func markPlayed(_ buffer: Buffer, generation completionGeneration: Int) -> Bool {
    markPlayedResult(buffer, generation: completionGeneration) != nil
  }

  /// Accepts one physical playback completion and returns the resulting queue
  /// metadata. Stale callbacks from a prior configuration/replacement/stop
  /// are rejected before they can produce progress or idle notifications.
  @discardableResult
  func markPlayedResult(
    _ buffer: Buffer,
    generation completionGeneration: Int
  ) -> Completion? {
    guard completionGeneration == generation else { return nil }
    if let index = scheduledBuffers.firstIndex(where: { $0 === buffer }) {
      scheduledBuffers.remove(at: index)
      return Completion(
        generation: generation,
        remainingBufferCount: scheduledBuffers.count)
    }
    return nil
  }

  func buffersToReplayAfterConfigurationChange() -> [Buffer] {
    let buffers = scheduledBuffers
    generation += 1
    scheduledBuffers.removeAll()
    return buffers
  }

  func clearForExplicitStop() {
    generation += 1
    scheduledBuffers.removeAll()
  }
}

/// Progress emitted after one queued PCM buffer has physically played.
///
/// `playbackEpoch` identifies the scheduled buffer and is monotonic within a
/// live queue generation; earlier epochs are valid progress while a later
/// buffer remains queued. Consumers should fence the lifecycle with
/// `queueGeneration` and their active output lease, then use `isIdle` only for
/// the final callback. `queueGeneration` changes on configuration replay and
/// explicit stop, fencing callbacks from an old turn or replacement.
struct StreamingPCMPlaybackProgress: Equatable, Sendable {
  let playbackEpoch: Int
  let queueGeneration: Int
  let remainingBufferCount: Int

  var isIdle: Bool { remainingBufferCount == 0 }
}

/// Keeps non-I/O audio units ready for the largest render slice macOS may ask
/// them to process after an output-route or sample-rate change.
///
/// CoreAudio can retain a route-specific `maximumFramesToRender` when an
/// `AVAudioEngine` graph is rebuilt. A later 512-frame render against a stale
/// 480-frame ceiling fails with `kAudioUnitErr_TooManyFramesToProcess`; the
/// player remains nominally running, but no `.dataPlayedBack` callback arrives.
/// Apple documents 4096 frames as the safe capacity for non-I/O units. This
/// must be applied while render resources are deallocated.
enum StreamingPCMRenderCapacity {
  static let minimumFrames: AUAudioFrameCount = 4096

  @discardableResult
  static func configure(units: [AUAudioUnit]) -> [AUAudioFrameCount] {
    units.map { unit in
      if !unit.renderResourcesAllocated, unit.maximumFramesToRender < minimumFrames {
        unit.maximumFramesToRender = minimumFrames
      }
      return unit.maximumFramesToRender
    }
  }
}

private final class DeferredConfigurationRecoveryAction: @unchecked Sendable {
  let action: () -> Void

  init(_ action: @escaping () -> Void) {
    self.action = action
  }
}

final class DeferredConfigurationRecovery: @unchecked Sendable {
  typealias MainQueueScheduler = @Sendable (@escaping @Sendable () -> Void) -> Void

  private let lock = NSLock()
  private let onMainQueue: MainQueueScheduler
  private var isPending = false
  private var generation = 0

  init(
    onMainQueue: @escaping MainQueueScheduler = { action in
      DispatchQueue.main.async(execute: action)
    }
  ) {
    self.onMainQueue = onMainQueue
  }

  func schedule(action: @escaping () -> Void) {
    let scheduledGeneration: Int
    lock.lock()
    guard !isPending else {
      lock.unlock()
      return
    }
    isPending = true
    generation += 1
    scheduledGeneration = generation
    lock.unlock()

    let actionBox = DeferredConfigurationRecoveryAction(action)
    onMainQueue { [weak self, actionBox] in
      guard self?.isPendingRecovery(generation: scheduledGeneration) == true else { return }
      actionBox.action()
      self?.finishPendingRecovery(generation: scheduledGeneration)
    }
  }

  func cancel() {
    lock.lock()
    generation += 1
    isPending = false
    lock.unlock()
  }

  private func isPendingRecovery(generation scheduledGeneration: Int) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    return isPending && generation == scheduledGeneration
  }

  private func finishPendingRecovery(generation scheduledGeneration: Int) {
    lock.lock()
    if generation == scheduledGeneration {
      isPending = false
    }
    lock.unlock()
  }
}

/// Plays streamed mono PCM16 audio incrementally (OpenAI Realtime / Gemini Live
/// output is 24 kHz). Feed chunks with `enqueue(_:)`; they play back-to-back in
/// arrival order. Used by `RealtimeHubController` to play the realtime model's
/// spoken response as it streams in.
///
/// Ported from the `feature/gpt-realtime` worktree's `LiveVoiceSession` audio
/// path (path adapted to the `desktop/macos/…` layout).
final class StreamingPCMPlayer: @unchecked Sendable {
  private let engine = AVAudioEngine()
  private let player = AVAudioPlayerNode()
  private let format: AVAudioFormat
  private var configObserver: NSObjectProtocol?
  private let playbackQueue = StreamingPCMPlaybackQueue<AVAudioPCMBuffer>()
  private let configurationRecovery = DeferredConfigurationRecovery()
  private(set) var playbackEpoch = 0
  /// Queue generation changes whenever the scheduled tail is invalidated.
  /// Exposed so the lifecycle owner can fence progress callbacks without
  /// requiring equality with the per-buffer `playbackEpoch`.
  private(set) var playbackQueueGeneration = 0
  /// Number of PCM buffers still awaiting a physical completion. This is
  /// queue metadata only; it contains no audio content.
  var scheduledBufferCount: Int { playbackQueue.scheduledBufferCount }
  /// Bounded render metadata for diagnostics and regression verification.
  private(set) var renderCapacities: [AUAudioFrameCount] = []
  var onPlaybackScheduled: ((Int) -> Void)?
  /// Called once for every valid physical `.dataPlayedBack` completion,
  /// including non-final buffers. `onPlaybackIdle` remains final-only.
  var onPlaybackProgress: ((StreamingPCMPlaybackProgress) -> Void)?
  var onPlaybackIdle: ((Int) -> Void)?

  init(sampleRate: Double = 24000) {
    // Float32 mono at the source rate; the mixer resamples to the device rate.
    format = AVAudioFormat(
      commonFormat: .pcmFormatFloat32, sampleRate: sampleRate, channels: 1, interleaved: false)!
    engine.attach(player)
    engine.connect(player, to: engine.mainMixerNode, format: format)
    configureRenderCapacity()
    // Output-level tap for the notch speaking animation. Tapping the mixer
    // (not enqueue-time RMS) keeps the visual in sync with what is audibly
    // playing rather than leading it by the scheduled-queue depth. The tap
    // callback runs on an audio thread; only the cheap RMS math happens there.
    engine.mainMixerNode.installTap(
      onBus: 0, bufferSize: 1024, format: engine.mainMixerNode.outputFormat(forBus: 0)
    ) { buffer, _ in
      let level = Self.rmsLevel(of: buffer)
      DispatchQueue.main.async {
        AudioLevelMonitor.shared.updateVoicePlaybackLevel(level)
      }
    }
    // An audio configuration change (another process grabbing the audio device, a
    // device/sample-rate change, a Bluetooth A2DP↔HFP flip, etc.) STOPS the engine
    // mid-stream — that's what cuts the reply off and can leave the engine in a
    // half-dead state (isRunning=true but no output) that silences later turns.
    // Fully tear down + rebuild the node graph and restart so playback always
    // recovers. (The PTT path also avoids the BT flip by capturing from the
    // built-in mic when output is Bluetooth — see PushToTalkManager.)
    configObserver = NotificationCenter.default.addObserver(
      forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main
    ) { [weak self] _ in
      guard let self = self else { return }
      self.configurationRecovery.schedule { [weak self] in
        guard let self = self else { return }
        self.rebuildAfterConfigurationChange()
      }
    }
  }

  deinit {
    if let observer = configObserver {
      NotificationCenter.default.removeObserver(observer)
    }
  }

  /// Ensure the engine + player are actually running before scheduling. Checking
  /// the real `isRunning`/`isPlaying` state (not a one-shot flag) is what makes
  /// playback survive past the first turn: AVAudioEngine auto-suspends when idle
  /// after a reply finishes, so later turns must restart it.
  private func ensureRunning() -> Bool {
    if !engine.isRunning {
      engine.prepare()
      do {
        try engine.start()
        log(
          "StreamingPCMPlayer: engine started, isRunning=\(engine.isRunning), outRate=\(engine.outputNode.outputFormat(forBus: 0).sampleRate)"
        )
      } catch {
        log("StreamingPCMPlayer: engine start FAILED: \(error.localizedDescription)")
        return false
      }
    }
    if !player.isPlaying {
      player.play()
    }
    return player.isPlaying
  }

  private func rebuildAfterConfigurationChange() {
    log("StreamingPCMPlayer: audio config changed — rebuilding engine")
    let buffersToReplay = playbackQueue.buffersToReplayAfterConfigurationChange()
    playbackQueueGeneration = playbackQueue.generation
    player.stop()
    engine.stop()
    engine.disconnectNodeOutput(player)
    engine.connect(player, to: engine.mainMixerNode, format: format)
    configureRenderCapacity()
    _ = ensureRunning()
    for buffer in buffersToReplay {
      schedule(buffer)
    }
  }

  private func configureRenderCapacity() {
    renderCapacities = StreamingPCMRenderCapacity.configure(
      units: [player.auAudioUnit, engine.mainMixerNode.auAudioUnit])
    if renderCapacities.contains(where: { $0 < StreamingPCMRenderCapacity.minimumFrames }) {
      log("StreamingPCMPlayer: render capacity remained below 4096 frames: \(renderCapacities)")
    }
  }

  /// `data` = little-endian Int16 PCM, mono, at the configured sample rate.
  @discardableResult
  func enqueue(_ data: Data) -> Bool {
    let sampleCount = data.count / 2
    guard sampleCount > 0,
      let buffer = AVAudioPCMBuffer(
        pcmFormat: format, frameCapacity: AVAudioFrameCount(sampleCount))
    else { return false }
    buffer.frameLength = AVAudioFrameCount(sampleCount)
    let channel = buffer.floatChannelData![0]
    data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
      let src = raw.bindMemory(to: Int16.self)
      for i in 0..<sampleCount {
        channel[i] = max(-1.0, min(1.0, Float(src[i]) / 32768.0))
      }
    }
    guard ensureRunning() else { return false }
    schedule(buffer)
    return true
  }

  private func schedule(_ buffer: AVAudioPCMBuffer) {
    playbackEpoch += 1
    let scheduledPlaybackEpoch = playbackEpoch
    onPlaybackScheduled?(scheduledPlaybackEpoch)
    let generation = playbackQueue.appendScheduled(buffer)
    // AVAudioPCMBuffer is not Sendable; box it so the main-actor completion hop
    // can carry it across the concurrency boundary.
    let bufferBox = PCMBufferBox(buffer: buffer)
    player.scheduleBuffer(buffer, completionCallbackType: .dataPlayedBack) { [weak self] _ in
      guard let self else { return }
      DispatchQueue.main.async {
        guard
          let completion = self.playbackQueue.markPlayedResult(
            bufferBox.buffer, generation: generation)
        else { return }
        self.onPlaybackProgress?(
          StreamingPCMPlaybackProgress(
            playbackEpoch: scheduledPlaybackEpoch,
            queueGeneration: completion.generation,
            remainingBufferCount: completion.remainingBufferCount))
        if completion.isIdle {
          self.onPlaybackIdle?(scheduledPlaybackEpoch)
        }
      }
    }
  }

  func stop() {
    playbackEpoch += 1
    configurationRecovery.cancel()
    playbackQueue.clearForExplicitStop()
    playbackQueueGeneration = playbackQueue.generation
    player.stop()
    engine.stop()
    DispatchQueue.main.async {
      AudioLevelMonitor.shared.updateVoicePlaybackLevel(0)
    }
  }

  /// Root-mean-square level of a float PCM buffer across all channels, 0…1.
  static func rmsLevel(of buffer: AVAudioPCMBuffer) -> Float {
    guard let channels = buffer.floatChannelData, buffer.frameLength > 0 else { return 0 }
    let channelCount = Int(buffer.format.channelCount)
    let frames = Int(buffer.frameLength)
    var sum: Float = 0
    for channel in 0..<channelCount {
      let samples = channels[channel]
      for frame in 0..<frames {
        let sample = samples[frame]
        sum += sample * sample
      }
    }
    return min(1, sqrt(sum / Float(frames * channelCount)))
  }
}
