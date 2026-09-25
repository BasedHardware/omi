import Foundation

/// Visible Interject reply surface: chip, classification attach, and ledger write.
///
/// Silent chat provenance still uses the 30-day durable interval. This window
/// is the ~60s voice-context bound — a card with `provenanceRef` must not keep
/// showing "replying to:" or attaching classification for a month.
enum InterjectReplyWindow {
  static let duration: TimeInterval = 60

  static func contains(createdAt: Date, now: Date = Date()) -> Bool {
    now.timeIntervalSince(createdAt) <= duration
  }
}
