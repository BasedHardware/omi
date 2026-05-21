import Foundation

struct BackgroundTranscriptionConfiguration: Equatable {
  var sampleRate: Int = 16000
  var maxChunkDuration: TimeInterval = 15.0
  var minChunkDuration: TimeInterval = 1.0
  var overlapDuration: TimeInterval = 1.0
  var silenceWindowDuration: TimeInterval = 0.35
  var silenceAmplitudeThreshold: Int = 256
  var speechPeakAmplitudeThreshold: Int = 512
  var speechRMSAmplitudeThreshold: Int = 64
  var maxPendingChunks: Int = 4

  var bytesPerSample: Int { 2 }

  func byteCount(for duration: TimeInterval) -> Int {
    max(0, Int(duration * Double(sampleRate)) * bytesPerSample)
  }

  func alignedByteCount(for duration: TimeInterval) -> Int {
    byteCount(for: duration).alignedToSample
  }
}

extension Int {
  var alignedToSample: Int {
    self - (self % 2)
  }
}
