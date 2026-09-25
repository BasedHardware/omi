import Foundation

struct JITAmbientNanoUsage: Equatable, Sendable {
  let used: Int
  let lastSpentAt: Date?
}

struct JITAmbientPacingInput: Equatable, Sendable {
  let usedToday: Int
  let budget: Int
  let lastSpentAt: Date?
  let now: Date
  let derivedIntentMatched: Bool
}

enum JITAmbientPacingDecision: Equatable, Sendable {
  case spend
  case deferred(reason: String)
  case exhausted
}

/// Spreads the ambient nano budget across the local day instead of spending it
/// on the first novel contexts after midnight.
///
/// Measured on the owner account (2026-08-30/31): all eight nano triages of the
/// day were consumed within about one minute of the first activity after local
/// midnight, leaving the lane dead for the remaining ~23 hours. This policy is
/// pure and keeps the same server-authoritative daily totals; it only decides
/// *when* a triage may be bought and reserves part of the budget for contexts
/// that match standing intent the user already expressed.
enum JITAmbientPacingPolicy {
  /// Triages that may be bought back-to-back at the start of a budget day.
  static let burstAllowance = 2
  /// Budget kept for derived-intent matches so late-day intent always has spend.
  static let reservedForDerivedIntent = 2
  /// The spacing denominator: eight triages spread over a sixteen-hour day is
  /// one every two hours. A real active-hours model can replace this constant
  /// without changing callers.
  static let activeDaySeconds: TimeInterval = 16 * 60 * 60

  static func spacing(budget: Int) -> TimeInterval {
    activeDaySeconds / Double(max(budget, 1))
  }

  static func decide(_ input: JITAmbientPacingInput) -> JITAmbientPacingDecision {
    guard input.budget > 0, input.usedToday < input.budget else { return .exhausted }
    if input.derivedIntentMatched {
      // Standing intent is the JIT signal: it bypasses spacing, never the cap.
      return .spend
    }
    if input.usedToday >= max(0, input.budget - reservedForDerivedIntent) {
      return .deferred(reason: "ambient_reserved_for_intent")
    }
    if input.usedToday < burstAllowance { return .spend }
    if let last = input.lastSpentAt, input.now.timeIntervalSince(last) < spacing(budget: input.budget) {
      return .deferred(reason: "ambient_paced")
    }
    return .spend
  }
}
