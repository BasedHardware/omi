import Foundation

/// Human-pacing math for autonomous AI Clone replies — how long a real person would
/// plausibly take to *read* an incoming text and to *type* each reply bubble. Used only
/// by the autonomous send path (Draft-Review approvals were already human-paced by the
/// approval itself). Pure functions with explicit bounds so tests can pin them.
enum AICloneHumanizer {

  /// Bounds shared by the delay functions (seconds). Public for tests.
  static let minReadingDelay: TimeInterval = 0.8
  static let maxReadingDelay: TimeInterval = 6.0
  static let minTypingDelay: TimeInterval = 0.9
  static let maxTypingDelay: TimeInterval = 9.0

  /// How long to "read" an incoming message before doing anything: a short base plus
  /// per-character reading time, with jitter so repeated replies never look metronomic.
  static func readingDelay(
    forIncoming text: String, jitter: ClosedRange<Double> = 0.75...1.3
  ) -> TimeInterval {
    let seconds = 1.0 + Double(text.count) * 0.03
    return clamp(seconds * .random(in: jitter), min: minReadingDelay, max: maxReadingDelay)
  }

  /// How long to "type" one reply bubble: per-character typing time (casual-texting
  /// speed, ~6-7 chars/sec) plus a small compose pause, with jitter. Long bubbles cap
  /// out — people paste/settle into flow — so a wall of text never stalls for minutes.
  static func typingDelay(
    forBubble text: String, jitter: ClosedRange<Double> = 0.8...1.25
  ) -> TimeInterval {
    let seconds = 0.6 + Double(text.count) * 0.15
    return clamp(seconds * .random(in: jitter), min: minTypingDelay, max: maxTypingDelay)
  }

  private static func clamp(_ value: Double, min lo: Double, max hi: Double) -> Double {
    Swift.min(hi, Swift.max(lo, value))
  }
}
