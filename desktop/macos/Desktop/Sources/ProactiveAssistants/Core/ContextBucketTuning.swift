import Foundation

/// Named tuning values for context bucket capture.
///
/// These govern capture, so they stay on the device rather than moving to the
/// backend with the readable fact projection. They are gathered here so the
/// tradeoff each one encodes is stated once, in one place, instead of being
/// rediscovered from a bare number at its use site.
enum ContextBucketTuning {
  /// How far back `resolveBucketID` looks for a prior completed visit before it
  /// will mint a bucket for a new subject.
  ///
  /// The gate exists so a window seen exactly once never becomes a bucket —
  /// most windows are incidental, and bucketing them would bury real work in
  /// noise. The cost is that work on a cadence slower than this window never
  /// accumulates context: each visit looks like the first one.
  ///
  /// Widening this admits slower-cadence work at the cost of more buckets;
  /// that is a product tradeoff, so the value is deliberately unchanged here
  /// and only given a name and a rationale.
  static let coldStartLookback: TimeInterval = 7 * 24 * 60 * 60

  /// Completed visits required inside `coldStartLookback` before a new subject
  /// earns a bucket. One means "seen at least twice, counting this visit".
  static let coldStartMinimumVisits = 1
}
