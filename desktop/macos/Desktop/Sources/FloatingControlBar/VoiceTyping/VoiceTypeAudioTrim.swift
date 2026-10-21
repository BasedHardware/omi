import Foundation

/// Trims the quiet lead-in from a push-to-talk buffer before it is decoded.
///
/// A hold starts at key-down, not when the user speaks, so a locked turn can
/// open with seconds of room tone. The recognizer decodes that silence into
/// invented words rather than an empty string, which corrupts the wake-word
/// check at the start of the turn.
enum VoiceTypeAudioTrim {

  /// RMS below this (of Int16 full scale) is room tone, not speech.
  static let speechRMSThreshold: Double = 350
  private static let windowSamples = 320  // 20 ms at 16 kHz
  /// Kept in front of the first loud window so the decoder still hears the
  /// attack of the first consonant.
  private static let preRollSamples = 1_600  // 100 ms

  /// The least voiced audio worth decoding on its own: 0.5 s at 16 kHz s16le.
  /// Below this there is no word to recover, only a breath, and the on-device
  /// decoder answers a breath with an invented phrase ("Thank you.").
  static let minimumDecodableSpeechBytes = 16_000

  /// Bytes of `pcm16k` that lie in 20 ms windows at speech level — how much
  /// of a buffer is actually voice, as opposed to the pauses around it.
  static func speechBytes(in pcm16k: Data) -> Int {
    let sampleCount = pcm16k.count / 2
    guard sampleCount >= windowSamples else { return 0 }
    return pcm16k.withUnsafeBytes { raw -> Int in
      let samples = raw.bindMemory(to: Int16.self)
      var loudWindows = 0
      var start = 0
      while start + windowSamples <= sampleCount {
        var sumSquares = 0.0
        for index in start..<(start + windowSamples) {
          let value = Double(Int16(littleEndian: samples[index]))
          sumSquares += value * value
        }
        if (sumSquares / Double(windowSamples)).squareRoot() >= speechRMSThreshold { loudWindows += 1 }
        start += windowSamples
      }
      return loudWindows * windowSamples * 2
    }
  }

  /// - Parameter pcm16k: raw s16le 16 kHz mono.
  /// - Returns: the buffer from just before the first speech onward, or empty
  ///   when the whole buffer is quiet.
  static func trimmingLeadingSilence(_ pcm16k: Data) -> Data {
    let sampleCount = pcm16k.count / 2
    guard sampleCount >= windowSamples else { return Data() }

    return pcm16k.withUnsafeBytes { raw -> Data in
      let samples = raw.bindMemory(to: Int16.self)
      var window = 0
      while (window + 1) * windowSamples <= sampleCount {
        var sumSquares = 0.0
        let start = window * windowSamples
        for index in start..<(start + windowSamples) {
          let value = Double(Int16(littleEndian: samples[index]))
          sumSquares += value * value
        }
        if (sumSquares / Double(windowSamples)).squareRoot() >= speechRMSThreshold {
          let firstSample = max(0, start - preRollSamples)
          // Relative to `startIndex`: a `Data` produced by a slice does not
          // start at zero, and an absolute range would trap.
          let lower = pcm16k.startIndex + firstSample * 2
          return pcm16k.subdata(in: lower..<pcm16k.endIndex)
        }
        window += 1
      }
      return Data()
    }
  }

  /// The opening of a turn, ready for a wake-word decode: leading room tone
  /// dropped, then at most `maxBytes`. Always zero-indexed, since every
  /// consumer here indexes from zero.
  static func opening(of pcm16k: Data, maxBytes: Int) -> Data {
    let trimmed = trimmingLeadingSilence(pcm16k)
    return Data(trimmed.prefix(maxBytes))
  }
}
