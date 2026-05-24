import Foundation

struct BackgroundTranscriptionConfiguration: Equatable {
  var sampleRate: Int = 16000
  var maxChunkDuration: TimeInterval = 15.0
  var minChunkDuration: TimeInterval = 1.0
  var overlapDuration: TimeInterval = 0.5
  var silenceWindowDuration: TimeInterval = 0.35
  var silenceAmplitudeThreshold: Int = 256
  var speechPeakAmplitudeThreshold: Int = 512
  var speechRMSAmplitudeThreshold: Int = 64
  var maxPendingChunks: Int = 4
  var maxChunkTranscriptionAttempts: Int = 3
  var requiresSpeechBeforeUpload: Bool = false
  var speechActivityDetection = SpeechActivityDetectionConfiguration()
  var usesSilenceAwareChunking: Bool {
    minChunkDuration < maxChunkDuration
  }

  var bytesPerSample: Int { 2 }

  func byteCount(for duration: TimeInterval) -> Int {
    max(0, Int(duration * Double(sampleRate)) * bytesPerSample)
  }

  func alignedByteCount(for duration: TimeInterval) -> Int {
    byteCount(for: duration).alignedToSample
  }

  var maxChunksPerAppend: Int {
    1
  }

  static var cloudBatch: BackgroundTranscriptionConfiguration {
    fixedFifteenSecondCloudBatch
  }

  static var fixedFifteenSecondCloudBatch: BackgroundTranscriptionConfiguration {
    BackgroundTranscriptionConfiguration(
      maxChunkDuration: 15.0,
      minChunkDuration: 15.0,
      overlapDuration: 0.5,
      maxPendingChunks: 8,
      maxChunkTranscriptionAttempts: 3,
      requiresSpeechBeforeUpload: true,
      speechActivityDetection: SpeechActivityDetectionConfiguration(
        windowDuration: 0.02,
        minimumSpeechDuration: 0.75,
        peakAmplitudeThreshold: 900,
        rmsAmplitudeThreshold: 180,
        maximumSpeechZeroCrossingRate: 0.35
      )
    )
  }

  static var silenceAwareCloudBatchCandidate: BackgroundTranscriptionConfiguration {
    var configuration = fixedFifteenSecondCloudBatch
    configuration.minChunkDuration = 6.0
    configuration.silenceWindowDuration = 0.35
    return configuration
  }
}

extension Int {
  var alignedToSample: Int {
    self - (self % 2)
  }
}
