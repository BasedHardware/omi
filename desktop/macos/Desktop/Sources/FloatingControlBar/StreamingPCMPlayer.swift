import AVFoundation
import Foundation

/// Plays streamed mono PCM16 audio incrementally (OpenAI Realtime / Gemini Live
/// output is 24 kHz). Feed chunks with `enqueue(_:)`; they play back-to-back in
/// arrival order. Used by `RealtimeHubController` to play the realtime model's
/// spoken response as it streams in.
///
/// Ported from the `feature/gpt-realtime` worktree's `LiveVoiceSession` audio
/// path (path adapted to the `desktop/macos/…` layout).
final class StreamingPCMPlayer {
  private let engine = AVAudioEngine()
  private let player = AVAudioPlayerNode()
  private let format: AVAudioFormat
  private var configObserver: NSObjectProtocol?

  /// Smoothed 0…1 output amplitude, delivered on the main thread (~40×/s) while the
  /// engine runs. Driven by a tap on the mixer so it tracks what's *actually audible*,
  /// not what's been buffered ahead. Used to make the speaking waveform audio-reactive.
  var onLevel: ((Float) -> Void)?
  /// Fires on the main thread when playback starts (false→true) and when the queue
  /// fully drains (true→false). Lets the caller mark "speaking" precisely — including
  /// the silent tail after the last chunk arrives but before it finishes playing.
  var onPlayingChanged: ((Bool) -> Void)?

  /// Outstanding scheduled buffers (incremented on enqueue, decremented when each
  /// finishes). Guarded by `bufferLock` because completion handlers run off-main.
  private var pendingBuffers = 0
  private let bufferLock = NSLock()
  private var isPlayingState = false
  // Exponential moving average of the output RMS (smoothed so the waveform never jitters).
  private var smoothedLevel: Float = 0
  // Last value handed to `onLevel`, so we skip main-thread hops while the level is flat
  // (e.g. the silent tail of a reply) instead of publishing the same number ~40×/s.
  private var lastDispatchedLevel: Float = -1
  private var levelTapInstalled = false

  init(sampleRate: Double = 24000) {
    // Float32 mono at the source rate; the mixer resamples to the device rate.
    format = AVAudioFormat(
      commonFormat: .pcmFormatFloat32, sampleRate: sampleRate, channels: 1, interleaved: false)!
    engine.attach(player)
    engine.connect(player, to: engine.mainMixerNode, format: format)
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
      log("StreamingPCMPlayer: audio config changed — rebuilding engine")
      self.player.stop()
      self.engine.stop()
      // The rebuilt graph loses the old tap; let ensureRunning() reinstall it.
      self.removeLevelTap()
      self.engine.disconnectNodeOutput(self.player)
      self.engine.connect(self.player, to: self.engine.mainMixerNode, format: self.format)
      self.ensureRunning()
    }
  }

  deinit {
    if let observer = configObserver {
      NotificationCenter.default.removeObserver(observer)
    }
  }

  /// Tap the mixer output once the engine is live so `onLevel` reflects the audio the
  /// user actually hears. Cheap: one RMS pass per ~1024-frame buffer, EMA-smoothed.
  private func installLevelTapIfNeeded() {
    guard !levelTapInstalled, engine.isRunning else { return }
    levelTapInstalled = true
    engine.mainMixerNode.installTap(onBus: 0, bufferSize: 1024, format: nil) {
      [weak self] buffer, _ in
      guard let self, self.onLevel != nil, let data = buffer.floatChannelData else { return }
      let frames = Int(buffer.frameLength)
      guard frames > 0 else { return }
      let samples = data[0]
      var sumSquares: Float = 0
      for i in 0..<frames { sumSquares += samples[i] * samples[i] }
      let rms = (sumSquares / Float(frames)).squareRoot()
      // Normalize: speech RMS is small, so apply gain and clamp. Attack fast, release
      // slow so the bars rise crisply with the voice but settle smoothly between words.
      let target = min(1.0, rms * 3.2)
      let alpha: Float = target > self.smoothedLevel ? 0.35 : 0.12
      self.smoothedLevel += (target - self.smoothedLevel) * alpha
      let out = self.smoothedLevel
      // Only hop to main when the level actually moved — flat/silent stretches stay quiet.
      guard abs(out - self.lastDispatchedLevel) > 0.01 else { return }
      self.lastDispatchedLevel = out
      DispatchQueue.main.async { self.onLevel?(out) }
    }
  }

  /// Detach the level tap (call when playback stops; reinstalled on the next play).
  private func removeLevelTap() {
    guard levelTapInstalled else { return }
    engine.mainMixerNode.removeTap(onBus: 0)
    levelTapInstalled = false
    smoothedLevel = 0
    lastDispatchedLevel = -1
  }

  /// Ensure the engine + player are actually running before scheduling. Checking
  /// the real `isRunning`/`isPlaying` state (not a one-shot flag) is what makes
  /// playback survive past the first turn: AVAudioEngine auto-suspends when idle
  /// after a reply finishes, so later turns must restart it.
  private func ensureRunning() {
    if !engine.isRunning {
      engine.prepare()
      do {
        try engine.start()
        log(
          "StreamingPCMPlayer: engine started, isRunning=\(engine.isRunning), outRate=\(engine.outputNode.outputFormat(forBus: 0).sampleRate)"
        )
      } catch {
        log("StreamingPCMPlayer: engine start FAILED: \(error.localizedDescription)")
        return
      }
    }
    if !player.isPlaying {
      player.play()
    }
    installLevelTapIfNeeded()
  }

  /// Adjust the outstanding-buffer count and emit `onPlayingChanged` on the edges.
  private func adjustPending(by delta: Int) {
    bufferLock.lock()
    pendingBuffers = max(0, pendingBuffers + delta)
    let nowPlaying = pendingBuffers > 0
    let changed = nowPlaying != isPlayingState
    if changed { isPlayingState = nowPlaying }
    bufferLock.unlock()
    guard changed else { return }
    DispatchQueue.main.async { [weak self] in self?.onPlayingChanged?(nowPlaying) }
  }

  /// `data` = little-endian Int16 PCM, mono, at the configured sample rate.
  func enqueue(_ data: Data) {
    ensureRunning()
    let sampleCount = data.count / 2
    guard sampleCount > 0,
      let buffer = AVAudioPCMBuffer(
        pcmFormat: format, frameCapacity: AVAudioFrameCount(sampleCount))
    else { return }
    buffer.frameLength = AVAudioFrameCount(sampleCount)
    let channel = buffer.floatChannelData![0]
    data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
      let src = raw.bindMemory(to: Int16.self)
      for i in 0..<sampleCount {
        channel[i] = max(-1.0, min(1.0, Float(src[i]) / 32768.0))
      }
    }
    adjustPending(by: 1)
    player.scheduleBuffer(buffer, completionHandler: { [weak self] in self?.adjustPending(by: -1) })
  }

  func stop() {
    removeLevelTap()  // no playback → no reason to keep tapping (reinstalled on next play)
    player.stop()
    engine.stop()
    bufferLock.lock()
    pendingBuffers = 0
    let wasPlaying = isPlayingState
    isPlayingState = false
    bufferLock.unlock()
    smoothedLevel = 0
    if wasPlaying {
      DispatchQueue.main.async { [weak self] in self?.onPlayingChanged?(false) }
    }
  }
}
