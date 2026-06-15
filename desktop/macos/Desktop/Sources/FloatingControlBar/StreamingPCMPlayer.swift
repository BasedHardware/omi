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
    player.scheduleBuffer(buffer, completionHandler: nil)
  }

  func stop() {
    player.stop()
    engine.stop()
  }
}
