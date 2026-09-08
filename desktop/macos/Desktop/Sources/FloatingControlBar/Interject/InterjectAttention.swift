import Foundation

/// Closed attention signal for timeout dismissals. Distinguishes a card the
/// user hovered (read and ignored) from one that timed out unseen.
enum InterjectAttention: String, CaseIterable, Sendable {
  case neverSeen = "never_seen"
  case readAndIgnored = "read_and_ignored"

  static func timeoutAttention(didHover: Bool) -> InterjectAttention {
    didHover ? .readAndIgnored : .neverSeen
  }
}
