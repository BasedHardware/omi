@preconcurrency import AVFoundation
@preconcurrency import AudioToolbox
import Foundation

enum ProgressiveMP3PlayerError: LocalizedError {
  case audioFileStream(OSStatus)
  case decoderUnavailable
  case conversion(String)
  case playbackUnavailable
  case unsupportedFormat

  var errorDescription: String? {
    switch self {
    case .audioFileStream(let status):
      return "MP3 parser failed (OSStatus \(status))"
    case .decoderUnavailable:
      return "The MP3 decoder could not be created"
    case .conversion(let message):
      return "MP3 decoding failed: \(message)"
    case .playbackUnavailable:
      return "The decoded TTS audio could not be scheduled for playback"
    case .unsupportedFormat:
      return "The streamed TTS response did not contain playable MP3 audio"
    }
  }
}

private final class SingleInputSupplyState: @unchecked Sendable {
  private let lock = NSLock()
  private var hasSuppliedInput = false

  func takeInput() -> Bool {
    lock.lock()
    defer { lock.unlock() }
    guard !hasSuppliedInput else { return false }
    hasSuppliedInput = true
    return true
  }
}

/// Incrementally parses MP3 packets, decodes them to small PCM buffers, and
/// schedules those buffers on the same route-resilient AVAudioEngine path as
/// realtime voice output. Compressed bytes are held only until a bounded
/// prebuffer is present; playback then advances while HTTP is still arriving.
@MainActor
final class ProgressiveMP3Player: ProgressiveAudioPlaying {
  var onStarted: (() -> Void)?
  var onDrained: ((TimeInterval) -> Void)?

  private struct PacketBatch {
    let data: Data
    let descriptions: [AudioStreamPacketDescription]
    let packetCount: UInt32
  }

  private static let minimumPrebufferBytes = 16 * 1024
  private static let outputSampleRate: Double = 24_000

  private let pcmPlayer: StreamingPCMPlayer
  private var fileStream: AudioFileStreamID?
  private var sourceFormat: AVAudioFormat?
  private var converter: AVAudioConverter?
  private var packetBatches: [PacketBatch] = []
  private var receivedCompressedBytes = 0
  private var scheduledMediaDuration: TimeInterval = 0
  private var streamFinished = false
  private var hasStarted = false
  private var hasDrained = false
  private var isStopped = false
  private var deferredError: Error?

  init(playbackRate: Float, manualRenderingForTesting: Bool = false) throws {
    pcmPlayer = StreamingPCMPlayer(
      sampleRate: Self.outputSampleRate,
      playbackRate: playbackRate)
    if manualRenderingForTesting {
      try pcmPlayer.enableManualRenderingForTesting()
    }
    pcmPlayer.onPlaybackIdle = { [weak self] _ in
      MainActor.assumeIsolated {
        self?.emitDrainIfReady()
      }
    }

    var stream: AudioFileStreamID?
    let status = AudioFileStreamOpen(
      Unmanaged.passUnretained(self).toOpaque(),
      progressiveMP3PropertyListener,
      progressiveMP3PacketsListener,
      kAudioFileMP3Type,
      &stream)
    guard status == noErr, let stream else {
      throw ProgressiveMP3PlayerError.audioFileStream(status)
    }
    fileStream = stream
  }

  func append(_ data: Data) throws {
    guard !isStopped, !streamFinished else { return }
    guard !data.isEmpty, let fileStream else { return }
    receivedCompressedBytes += data.count
    let status = data.withUnsafeBytes { bytes in
      AudioFileStreamParseBytes(
        fileStream,
        UInt32(bytes.count),
        bytes.baseAddress,
        [])
    }
    guard status == noErr else {
      throw ProgressiveMP3PlayerError.audioFileStream(status)
    }
    if let deferredError {
      throw deferredError
    }
    try decodePendingPacketsIfReady()
  }

  func finish() {
    guard !isStopped, !streamFinished else { return }
    streamFinished = true
    do {
      try decodePendingPacketsIfReady()
    } catch {
      deferredError = error
      packetBatches.removeAll()
    }
    emitDrainIfReady()
  }

  func stop() {
    guard !isStopped else { return }
    isStopped = true
    onStarted = nil
    onDrained = nil
    pcmPlayer.onPlaybackIdle = nil
    pcmPlayer.stop()
    if let fileStream {
      AudioFileStreamClose(fileStream)
      self.fileStream = nil
    }
    packetBatches.removeAll()
  }

  fileprivate func handleProperty(propertyID: AudioFileStreamPropertyID) {
    guard !isStopped, let fileStream else { return }
    switch propertyID {
    case kAudioFileStreamProperty_DataFormat:
      var description = AudioStreamBasicDescription()
      var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
      let status = AudioFileStreamGetProperty(fileStream, propertyID, &size, &description)
      guard status == noErr else {
        deferredError = ProgressiveMP3PlayerError.audioFileStream(status)
        return
      }
      guard let format = AVAudioFormat(streamDescription: &description) else {
        deferredError = ProgressiveMP3PlayerError.unsupportedFormat
        return
      }
      guard
        let outputFormat = AVAudioFormat(
          commonFormat: .pcmFormatFloat32,
          sampleRate: Self.outputSampleRate,
          channels: 1,
          interleaved: false)
      else {
        deferredError = ProgressiveMP3PlayerError.unsupportedFormat
        return
      }
      guard let converter = AVAudioConverter(from: format, to: outputFormat) else {
        deferredError = ProgressiveMP3PlayerError.decoderUnavailable
        return
      }
      sourceFormat = format
      self.converter = converter

    case kAudioFileStreamProperty_ReadyToProducePackets:
      copyMagicCookieIfPresent(from: fileStream)

    default:
      break
    }
  }

  fileprivate func handlePackets(
    data: Data,
    packetDescriptions: [AudioStreamPacketDescription],
    packetCount: UInt32
  ) {
    guard !isStopped, !data.isEmpty, packetCount > 0 else { return }
    packetBatches.append(
      PacketBatch(
        data: data,
        descriptions: packetDescriptions,
        packetCount: packetCount))
  }

  private func copyMagicCookieIfPresent(from stream: AudioFileStreamID) {
    guard let converter else { return }
    var cookieSize: UInt32 = 0
    var writable = DarwinBoolean(false)
    let infoStatus = AudioFileStreamGetPropertyInfo(
      stream,
      kAudioFileStreamProperty_MagicCookieData,
      &cookieSize,
      &writable)
    guard infoStatus == noErr, cookieSize > 0 else { return }
    var cookie = Data(count: Int(cookieSize))
    let readStatus = cookie.withUnsafeMutableBytes { bytes in
      guard let baseAddress = bytes.baseAddress else { return kAudio_ParamError }
      return AudioFileStreamGetProperty(
        stream,
        kAudioFileStreamProperty_MagicCookieData,
        &cookieSize,
        baseAddress)
    }
    if readStatus == noErr {
      converter.magicCookie = cookie
    }
  }

  private func decodePendingPacketsIfReady() throws {
    guard streamFinished || receivedCompressedBytes >= Self.minimumPrebufferBytes else { return }
    guard sourceFormat != nil, converter != nil else {
      if streamFinished { throw ProgressiveMP3PlayerError.unsupportedFormat }
      return
    }
    let batches = packetBatches
    packetBatches.removeAll(keepingCapacity: true)
    for batch in batches {
      try decode(batch)
    }
  }

  private func decode(_ batch: PacketBatch) throws {
    guard let sourceFormat, let converter else {
      throw ProgressiveMP3PlayerError.decoderUnavailable
    }
    let maximumPacketSize = max(
      1,
      batch.descriptions.map { Int($0.mDataByteSize) }.max()
        ?? Int(ceil(Double(batch.data.count) / Double(batch.packetCount))))
    let compressed = AVAudioCompressedBuffer(
      format: sourceFormat,
      packetCapacity: batch.packetCount,
      maximumPacketSize: maximumPacketSize)
    guard batch.data.count <= compressed.byteCapacity else {
      throw ProgressiveMP3PlayerError.unsupportedFormat
    }
    batch.data.withUnsafeBytes { bytes in
      if let baseAddress = bytes.baseAddress {
        memcpy(compressed.data, baseAddress, bytes.count)
      }
    }
    compressed.byteLength = UInt32(batch.data.count)
    compressed.packetCount = batch.packetCount
    if !batch.descriptions.isEmpty, let destination = compressed.packetDescriptions {
      batch.descriptions.withUnsafeBufferPointer { source in
        guard let baseAddress = source.baseAddress else { return }
        destination.update(from: baseAddress, count: source.count)
      }
    }

    let sourceDescription = sourceFormat.streamDescription.pointee
    let framesPerPacket = max(1, Int(sourceDescription.mFramesPerPacket))
    let sourceRate = max(1, sourceDescription.mSampleRate)
    let estimatedFrames =
      Int(ceil(Double(batch.packetCount) * Double(framesPerPacket) * Self.outputSampleRate / sourceRate))
    let outputCapacity = AVAudioFrameCount(max(4096, estimatedFrames + 4096))
    let outputFormat = converter.outputFormat
    guard let output = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: outputCapacity) else {
      throw ProgressiveMP3PlayerError.decoderUnavailable
    }

    let inputSupplyState = SingleInputSupplyState()
    var conversionError: NSError?
    let status = converter.convert(to: output, error: &conversionError) { _, inputStatus in
      guard inputSupplyState.takeInput() else {
        inputStatus.pointee = .noDataNow
        return nil
      }
      inputStatus.pointee = .haveData
      return compressed
    }
    if let conversionError {
      throw ProgressiveMP3PlayerError.conversion(conversionError.localizedDescription)
    }
    if status == .error {
      throw ProgressiveMP3PlayerError.conversion("the decoder returned an error")
    }
    guard output.frameLength > 0 else { return }
    guard pcmPlayer.enqueue(output) else {
      throw ProgressiveMP3PlayerError.playbackUnavailable
    }
    scheduledMediaDuration += TimeInterval(output.frameLength) / output.format.sampleRate
    if !hasStarted {
      hasStarted = true
      onStarted?()
    }
  }

  private func emitDrainIfReady() {
    guard streamFinished, pcmPlayer.scheduledBufferCount == 0, !hasDrained else { return }
    hasDrained = true
    onDrained?(scheduledMediaDuration)
  }
}

private let progressiveMP3PropertyListener: AudioFileStream_PropertyListenerProc = {
  clientData, _, propertyID, _ in
  let player = Unmanaged<ProgressiveMP3Player>.fromOpaque(clientData).takeUnretainedValue()
  MainActor.assumeIsolated {
    player.handleProperty(propertyID: propertyID)
  }
}

private let progressiveMP3PacketsListener: AudioFileStream_PacketsProc = {
  clientData, byteCount, packetCount, inputData, packetDescriptions in
  let player = Unmanaged<ProgressiveMP3Player>.fromOpaque(clientData).takeUnretainedValue()
  let data = Data(bytes: inputData, count: Int(byteCount))
  let descriptions: [AudioStreamPacketDescription]
  if let packetDescriptions {
    descriptions = Array(UnsafeBufferPointer(start: packetDescriptions, count: Int(packetCount)))
  } else {
    descriptions = []
  }
  MainActor.assumeIsolated {
    player.handlePackets(
      data: data,
      packetDescriptions: descriptions,
      packetCount: packetCount)
  }
}
