import Foundation

struct BackgroundAudioChunk: Equatable {
  let pcmData: Data
  let startTime: Double
  let isFinal: Bool
}

struct BackgroundAudioChunker {
  private let configuration: BackgroundTranscriptionConfiguration
  private var buffer = Data()
  private var bufferStartTime: Double?

  init(configuration: BackgroundTranscriptionConfiguration = BackgroundTranscriptionConfiguration()) {
    self.configuration = configuration
  }

  mutating func append(pcmData: Data, startTime: Double) -> [BackgroundAudioChunk] {
    guard !pcmData.isEmpty else { return [] }

    if buffer.isEmpty {
      bufferStartTime = startTime
    }
    buffer.append(pcmData)

    var chunks: [BackgroundAudioChunk] = []
    while let chunk = nextChunk(isFinal: false) {
      chunks.append(chunk)
    }
    return chunks
  }

  mutating func finishInput() -> [BackgroundAudioChunk] {
    guard !buffer.isEmpty else { return [] }
    let chunk = BackgroundAudioChunk(
      pcmData: buffer,
      startTime: bufferStartTime ?? 0,
      isFinal: true
    )
    buffer.removeAll(keepingCapacity: false)
    bufferStartTime = nil
    return [chunk]
  }

  private mutating func nextChunk(isFinal: Bool) -> BackgroundAudioChunk? {
    let minBytes = configuration.alignedByteCount(for: configuration.minChunkDuration)
    let maxBytes = configuration.alignedByteCount(for: configuration.maxChunkDuration)
    guard buffer.count >= minBytes else { return nil }

    let cutBytes: Int?
    if let silenceCut = firstSilenceCut(minBytes: minBytes, maxBytes: min(buffer.count, maxBytes)) {
      cutBytes = silenceCut
    } else if buffer.count >= maxBytes {
      cutBytes = maxBytes
    } else {
      cutBytes = nil
    }

    guard let cutBytes, cutBytes > 0 else { return nil }
    return cut(at: cutBytes, isFinal: isFinal)
  }

  private mutating func cut(at requestedCutBytes: Int, isFinal: Bool) -> BackgroundAudioChunk {
    let cutBytes = min(requestedCutBytes, buffer.count).alignedToSample
    let startTime = bufferStartTime ?? 0
    let chunk = BackgroundAudioChunk(
      pcmData: buffer.prefix(cutBytes),
      startTime: startTime,
      isFinal: isFinal
    )

    let overlapBytes = min(configuration.alignedByteCount(for: configuration.overlapDuration), cutBytes)
    let retainedStart = max(0, cutBytes - overlapBytes)
    let retained = buffer.suffix(buffer.count - retainedStart)
    buffer = Data(retained)
    bufferStartTime = startTime + Double(retainedStart / configuration.bytesPerSample) / Double(configuration.sampleRate)
    return chunk
  }

  private func firstSilenceCut(minBytes: Int, maxBytes: Int) -> Int? {
    let windowBytes = max(configuration.bytesPerSample, configuration.alignedByteCount(for: configuration.silenceWindowDuration))
    guard maxBytes >= minBytes + windowBytes else { return nil }

    var offset = minBytes.alignedToSample
    while offset + windowBytes <= maxBytes {
      if isSilentWindow(start: offset, byteCount: windowBytes), hasSpeech(before: offset) {
        return offset
      }
      offset += configuration.bytesPerSample
    }
    return nil
  }

  private func isSilentWindow(start: Int, byteCount: Int) -> Bool {
    guard start >= 0, start + byteCount <= buffer.count else { return false }
    var maxAmplitude = 0
    for offset in stride(from: start, to: start + byteCount, by: configuration.bytesPerSample) {
      maxAmplitude = max(maxAmplitude, sampleAmplitude(at: offset))
      if maxAmplitude > configuration.silenceAmplitudeThreshold {
        return false
      }
    }
    return true
  }

  private func hasSpeech(before endOffset: Int) -> Bool {
    guard endOffset > 0 else { return false }
    var peak = 0
    var sumSquares = 0.0
    var count = 0

    for offset in stride(from: 0, to: min(endOffset, buffer.count), by: configuration.bytesPerSample) {
      let amplitude = sampleAmplitude(at: offset)
      peak = max(peak, amplitude)
      sumSquares += Double(amplitude * amplitude)
      count += 1
    }

    guard count > 0 else { return false }
    let rms = sqrt(sumSquares / Double(count))
    return peak >= configuration.speechPeakAmplitudeThreshold
      || rms >= Double(configuration.speechRMSAmplitudeThreshold)
  }

  private func sampleAmplitude(at offset: Int) -> Int {
    guard offset + 1 < buffer.count else { return 0 }
    let low = UInt16(buffer[offset])
    let high = UInt16(buffer[offset + 1]) << 8
    let sample = Int16(bitPattern: low | high)
    return abs(Int(sample))
  }
}

extension Data {
  fileprivate func prefix(_ count: Int) -> Data {
    Data(self[startIndex..<index(startIndex, offsetBy: count)])
  }
}
