import Foundation

/// Pure core of the "visual stream" (smooth streaming, ref.
/// upstash.com/blog/smooth-streaming): decouples the network cadence from
/// the reading cadence. Deltas accumulate in `ChatProvider`'s streaming
/// buffer as fast as they arrive; this decides how many characters each
/// flush tick reveals so text "types" smoothly instead of jumping in
/// whole-chunk bursts.
///
/// Adaptive rate: a steady base of ~200 characters per second, accelerating
/// proportionally to the backlog so the visible text never trails the
/// backend by more than a few ticks — fast models drain quickly, slow
/// models still read as continuous typing.
enum SmoothStreamReveal {
  /// Base pace: ~5ms per character (~200 cps).
  static let msPerCharacter: Double = 5

  /// Backlog cap: with a large backlog, accelerate to drain it within at
  /// most this many ticks. At the ~35ms flush cadence, 4 ticks ≈ 140ms of
  /// maximum lag behind the backend.
  static let catchUpTicks: Double = 4

  /// How many characters to reveal on this tick.
  /// - remaining: characters still buffered (not yet shown).
  /// - elapsedMs: time since the previous tick.
  static func step(remaining: Int, elapsedMs: Double) -> Int {
    guard remaining > 0 else { return 0 }
    let base = elapsedMs / msPerCharacter
    let catchUp = Double(remaining) / catchUpTicks
    let step = Int(max(base, catchUp).rounded(.up))
    return min(remaining, max(1, step))
  }
}
