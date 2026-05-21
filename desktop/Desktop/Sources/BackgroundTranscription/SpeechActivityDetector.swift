import Foundation

struct SpeechActivityDetectionConfiguration: Equatable {
  var windowDuration: TimeInterval = 0.02
  var minimumSpeechDuration: TimeInterval = 0.25
  var peakAmplitudeThreshold: Int = 512
  var rmsAmplitudeThreshold: Int = 64
  var maximumSpeechZeroCrossingRate: Double = 0.35
}

struct SpeechActivityDecision: Equatable {
  enum Reason: String, Equatable {
    case speechDetected
    case emptyAudio
    case insufficientSpeech
    case energeticNonSpeech
  }

  let shouldUpload: Bool
  let reason: Reason
  let totalWindows: Int
  let energeticWindows: Int
  let speechLikeWindows: Int
  let rejectedHighZeroCrossingWindows: Int
  let maxPeakAmplitude: Int
  let maxRMSAmplitude: Double
}

struct SpeechActivityDetector {
  private let configuration: SpeechActivityDetectionConfiguration
  private let sampleRate: Int
  private let bytesPerSample: Int

  init(
    configuration: SpeechActivityDetectionConfiguration,
    sampleRate: Int,
    bytesPerSample: Int = 2
  ) {
    self.configuration = configuration
    self.sampleRate = sampleRate
    self.bytesPerSample = bytesPerSample
  }

  func evaluate(pcmData: Data) -> SpeechActivityDecision {
    guard !pcmData.isEmpty else {
      return SpeechActivityDecision(
        shouldUpload: false,
        reason: .emptyAudio,
        totalWindows: 0,
        energeticWindows: 0,
        speechLikeWindows: 0,
        rejectedHighZeroCrossingWindows: 0,
        maxPeakAmplitude: 0,
        maxRMSAmplitude: 0
      )
    }

    let windowBytes = max(bytesPerSample, alignedByteCount(for: configuration.windowDuration))
    let requiredSpeechWindows = max(
      1,
      Int(ceil(configuration.minimumSpeechDuration / configuration.windowDuration))
    )

    var totalWindows = 0
    var energeticWindows = 0
    var speechLikeWindows = 0
    var consecutiveSpeechLikeWindows = 0
    var rejectedHighZeroCrossingWindows = 0
    var maxPeakAmplitude = 0
    var maxRMSAmplitude = 0.0

    var offset = 0
    while offset < pcmData.count {
      let endOffset = min(offset + windowBytes, pcmData.count)
      let window = analyzeWindow(pcmData, start: offset, end: endOffset)
      totalWindows += 1
      maxPeakAmplitude = max(maxPeakAmplitude, window.peakAmplitude)
      maxRMSAmplitude = max(maxRMSAmplitude, window.rmsAmplitude)

      if window.isEnergetic(
        peakThreshold: configuration.peakAmplitudeThreshold,
        rmsThreshold: configuration.rmsAmplitudeThreshold
      ) {
        energeticWindows += 1
        if window.zeroCrossingRate <= configuration.maximumSpeechZeroCrossingRate {
          speechLikeWindows += 1
          consecutiveSpeechLikeWindows += 1
          if consecutiveSpeechLikeWindows >= requiredSpeechWindows {
            return SpeechActivityDecision(
              shouldUpload: true,
              reason: .speechDetected,
              totalWindows: totalWindows,
              energeticWindows: energeticWindows,
              speechLikeWindows: speechLikeWindows,
              rejectedHighZeroCrossingWindows: rejectedHighZeroCrossingWindows,
              maxPeakAmplitude: maxPeakAmplitude,
              maxRMSAmplitude: maxRMSAmplitude
            )
          }
        } else {
          consecutiveSpeechLikeWindows = 0
          rejectedHighZeroCrossingWindows += 1
        }
      } else {
        consecutiveSpeechLikeWindows = 0
      }

      offset += windowBytes
    }

    let reason: SpeechActivityDecision.Reason =
      energeticWindows > 0 && rejectedHighZeroCrossingWindows >= energeticWindows
      ? .energeticNonSpeech
      : .insufficientSpeech

    return SpeechActivityDecision(
      shouldUpload: false,
      reason: reason,
      totalWindows: totalWindows,
      energeticWindows: energeticWindows,
      speechLikeWindows: speechLikeWindows,
      rejectedHighZeroCrossingWindows: rejectedHighZeroCrossingWindows,
      maxPeakAmplitude: maxPeakAmplitude,
      maxRMSAmplitude: maxRMSAmplitude
    )
  }

  private func analyzeWindow(_ pcmData: Data, start: Int, end: Int) -> WindowActivity {
    var peak = 0
    var sumSquares = 0.0
    var sampleCount = 0
    var zeroCrossings = 0
    var previousSample: Int16?

    for offset in stride(from: start, to: end, by: bytesPerSample) {
      guard offset + 1 < pcmData.count else { break }
      let sample = sampleValue(in: pcmData, at: offset)
      let amplitude = abs(Int(sample))
      peak = max(peak, amplitude)
      sumSquares += Double(amplitude * amplitude)
      if let previousSample, crossesZero(previousSample, sample) {
        zeroCrossings += 1
      }
      previousSample = sample
      sampleCount += 1
    }

    guard sampleCount > 0 else {
      return WindowActivity(peakAmplitude: 0, rmsAmplitude: 0, zeroCrossingRate: 0)
    }
    let rms = sqrt(sumSquares / Double(sampleCount))
    let denominator = max(1, sampleCount - 1)
    return WindowActivity(
      peakAmplitude: peak,
      rmsAmplitude: rms,
      zeroCrossingRate: Double(zeroCrossings) / Double(denominator)
    )
  }

  private func alignedByteCount(for duration: TimeInterval) -> Int {
    (Int(duration * Double(sampleRate)) * bytesPerSample).alignedToSample
  }

  private func sampleValue(in pcmData: Data, at offset: Int) -> Int16 {
    let low = UInt16(pcmData[offset])
    let high = UInt16(pcmData[offset + 1]) << 8
    return Int16(bitPattern: low | high)
  }

  private func crossesZero(_ lhs: Int16, _ rhs: Int16) -> Bool {
    (lhs < 0 && rhs > 0) || (lhs > 0 && rhs < 0)
  }
}

private struct WindowActivity {
  let peakAmplitude: Int
  let rmsAmplitude: Double
  let zeroCrossingRate: Double

  func isEnergetic(peakThreshold: Int, rmsThreshold: Int) -> Bool {
    peakAmplitude >= peakThreshold || rmsAmplitude >= Double(rmsThreshold)
  }
}
