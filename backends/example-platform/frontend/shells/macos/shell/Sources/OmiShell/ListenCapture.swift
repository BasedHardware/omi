import AVFoundation
import Foundation

/// Policy for real microphone capture. Evidence audio must never install a tap
/// or call `requestAccess` — headless L3 has no TCC prompt surface.
enum ListenCapturePolicy {
  static func shouldInstallTap(evidenceAudioEnabled: Bool) -> Bool {
    !evidenceAudioEnabled
  }

  static func canRequestAccess(hasUsageDescription: Bool, evidenceAudioEnabled: Bool) -> Bool {
    hasUsageDescription && !evidenceAudioEnabled
  }

  static func tearsDownCapture(_ action: String) -> Bool {
    action == "stop" || action == "close"
  }
}

/// 16 kHz mono PCM16 matching the Listen handshake (`sample_rate=16000, codec=pcm16`).
enum ListenPcm16 {
  static let sampleRate: Double = 16_000
  static let channels: AVAudioChannelCount = 1
  static let bytesPerSample = 2
  static let chunkDurationMilliseconds = 100
  static var samplesPerChunk: Int {
    Int(sampleRate * Double(chunkDurationMilliseconds) / 1_000)
  }
  static var bytesPerChunk: Int { samplesPerChunk * bytesPerSample }

  static var targetFormat: AVAudioFormat {
    AVAudioFormat(
      commonFormat: .pcmFormatInt16, sampleRate: sampleRate, channels: channels, interleaved: true)!
  }

  static func convert(_ buffer: AVAudioPCMBuffer, using converter: AVAudioConverter) -> Data {
    if buffer.format.sampleRate == sampleRate,
      buffer.format.commonFormat == .pcmFormatInt16,
      buffer.format.channelCount == channels
    {
      return int16Data(from: buffer)
    }
    let ratio = targetFormat.sampleRate / max(buffer.format.sampleRate, 1)
    let capacity = AVAudioFrameCount((Double(buffer.frameLength) * ratio).rounded(.up) + 32)
    guard capacity > 0,
      let output = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: max(capacity, 1))
    else { return Data() }
    var submitted = false
    var error: NSError?
    let inputBlock: AVAudioConverterInputBlock = { _, status in
      if submitted {
        status.pointee = .noDataNow
        return nil
      }
      submitted = true
      status.pointee = .haveData
      return buffer
    }
    converter.convert(to: output, error: &error, withInputFrom: inputBlock)
    if error != nil { return Data() }
    return int16Data(from: output)
  }

  static func int16Data(from buffer: AVAudioPCMBuffer) -> Data {
    let frames = Int(buffer.frameLength)
    guard frames > 0, let channels = buffer.int16ChannelData else { return Data() }
    let channelCount = Int(buffer.format.channelCount)
    if buffer.format.isInterleaved {
      return Data(bytes: channels[0], count: frames * channelCount * MemoryLayout<Int16>.size)
    }
    var data = Data(count: frames * MemoryLayout<Int16>.size)
    data.withUnsafeMutableBytes { raw in
      guard let out = raw.bindMemory(to: Int16.self).baseAddress else { return }
      let source = channels[0]
      for index in 0..<frames { out[index] = source[index] }
    }
    return data
  }

  static func takeChunks(_ accumulator: inout Data) -> [Data] {
    var chunks: [Data] = []
    while accumulator.count >= bytesPerChunk {
      chunks.append(accumulator.prefix(bytesPerChunk))
      accumulator.removeSubrange(0..<bytesPerChunk)
    }
    return chunks
  }
}

/// Hardware capture → 16 kHz mono PCM16 chunks. Start/stop must run on the main thread.
final class ListenMicrophoneCapture {
  private let engine = AVAudioEngine()
  private let lock = NSLock()
  private var converter: AVAudioConverter?
  private var accumulator = Data()
  private var onChunk: ((Data) -> Void)?
  private var tapInstalled = false

  func start(onChunk: @escaping (Data) -> Void) -> Bool {
    stop()
    guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else { return false }
    guard AVCaptureDevice.default(for: .audio) != nil else { return false }
    let input = engine.inputNode
    let hardwareFormat = input.inputFormat(forBus: 0)
    guard hardwareFormat.sampleRate > 0, hardwareFormat.channelCount > 0 else { return false }
    guard let converter = AVAudioConverter(from: hardwareFormat, to: ListenPcm16.targetFormat)
    else { return false }
    lock.lock()
    self.converter = converter
    self.onChunk = onChunk
    accumulator.removeAll(keepingCapacity: false)
    lock.unlock()
    input.installTap(onBus: 0, bufferSize: 2_048, format: hardwareFormat) { [weak self] buffer, _ in
      self?.handle(buffer)
    }
    tapInstalled = true
    engine.prepare()
    do {
      try engine.start()
      return true
    } catch {
      stop()
      return false
    }
  }

  func stop() {
    if tapInstalled {
      engine.inputNode.removeTap(onBus: 0)
      tapInstalled = false
    }
    if engine.isRunning {
      engine.stop()
      engine.reset()
    }
    var leftover = Data()
    var callback: ((Data) -> Void)?
    lock.lock()
    leftover = accumulator
    accumulator.removeAll(keepingCapacity: false)
    callback = onChunk
    onChunk = nil
    converter = nil
    lock.unlock()
    if leftover.count >= ListenPcm16.bytesPerSample {
      callback?(leftover)
    }
  }

  private func handle(_ buffer: AVAudioPCMBuffer) {
    var outgoing: [Data] = []
    var callback: ((Data) -> Void)?
    lock.lock()
    callback = onChunk
    if let converter, callback != nil {
      accumulator.append(ListenPcm16.convert(buffer, using: converter))
      outgoing = ListenPcm16.takeChunks(&accumulator)
    }
    lock.unlock()
    guard let callback else { return }
    for chunk in outgoing where !chunk.isEmpty {
      callback(chunk)
    }
  }
}
