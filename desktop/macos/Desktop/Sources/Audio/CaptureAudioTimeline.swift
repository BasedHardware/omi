import Foundation

/// Keeps local ASR's sample clock aligned with a session that survives a closed capture gate.
/// Gaps contain no synthetic audio. A decode window ends before each gap so speech on its two
/// sides cannot become one utterance or give pre-gap words a post-gap timestamp.
struct CaptureAudioTimeline {
  private struct Gap {
    let afterSample: Int
    var seconds: TimeInterval
  }
  private var gaps: [Gap] = []
  private var pausedAt: Date?

  mutating func setPaused(_ paused: Bool, at now: Date, capturedSamples: Int) {
    if paused {
      if pausedAt == nil { pausedAt = now }
      return
    }
    guard let start = pausedAt else { return }
    pausedAt = nil
    let duration = now.timeIntervalSince(start)
    guard duration.isFinite, duration > 0 else { return }
    if let last = gaps.indices.last, gaps[last].afterSample == capturedSamples {
      gaps[last].seconds += duration
    } else {
      gaps.append(Gap(afterSample: capturedSamples, seconds: duration))
    }
  }

  func timestamp(at sample: Int, sampleRate: Int) -> TimeInterval {
    Double(sample) / Double(sampleRate)
      + gaps.lazy.filter { $0.afterSample <= sample }.reduce(0) { $0 + $1.seconds }
  }

  func samplesUntilNextGap(after sample: Int) -> Int? {
    gaps.first { $0.afterSample > sample }.map { $0.afterSample - sample }
  }
}
