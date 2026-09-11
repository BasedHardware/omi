import Foundation

/// Why an explicit "what's on my screen?" turn cannot use a fresh live capture
/// of the screen it is asking about.
enum ScreenContextFallbackUnavailable: Equatable {
  /// No loadable frame of a non-excluded app exists in the Rewind store
  /// (fresh install, capture off, or every recent row unreadable).
  case noAttachableFrame
  /// A frame exists but is older than the staleness bound, so presenting it
  /// as "my screen" would be a lie.
  case frameTooStale(ageSeconds: Int)
}

/// Which pixels an explicit current-screen request should present as evidence.
enum ScreenContextEvidenceSource: Equatable {
  /// A fresh capture scoped to this turn — the subject is on screen right now.
  case turnScopedLiveCapture
  /// The most recent frame of a non-excluded app, standing in for a screen
  /// Omi itself now occupies.
  case lastExternalFrame
  /// No honest evidence exists; the payload must say so instead of
  /// photographing Omi's own window.
  case unavailable(ScreenContextFallbackUnavailable)
}

/// Pure, clock-free decision layer for the one surface where "my screen" is
/// self-referential: a question typed into the main chat window.
///
/// The main composer lives in Omi's own window, so a live capture at send time
/// photographs Omi describing itself — measured at 19% of first screen
/// questions before the first-real-app card existed to route the moment
/// elsewhere (`FirstRealAppCardPolicy`). The periodic Rewind capture excludes
/// Omi's own app by name, which makes the newest frame in its store, by
/// construction, "what the user was looking at right before they summoned
/// Omi." Voice and floating surfaces ask while the user is *inside* the other
/// app, so there a turn-scoped live capture is still the correct subject.
///
/// Exactly the shape of `FirstRealAppCardPolicy`: the caller supplies inputs,
/// this decides, and everything with a clock stays outside (age is passed in,
/// never read here).
enum ScreenContextFallbackPolicy {
  /// A frame older than this no longer counts as "my screen" — a user who left
  /// Omi open for ten minutes does not mean the app from ten minutes ago.
  /// Sits above `staleCaptureThresholdSeconds` (60s) because the frame must
  /// also survive the tap-to-summon-to-send window of the first-real-app card.
  static let maxFallbackFrameAgeSeconds: TimeInterval = 120

  static func evidenceSource(
    turnOwner: ChatTurnOwner,
    lastExternalFrameAgeSeconds: TimeInterval?,
    maxAgeSeconds: TimeInterval = maxFallbackFrameAgeSeconds
  ) -> ScreenContextEvidenceSource {
    // Only the main chat is self-referential: its composer is the frontmost
    // thing on screen whenever its send fires. Every other surface interjects
    // from outside, where the live capture is the subject the user means.
    guard turnOwner == .mainChat else { return .turnScopedLiveCapture }
    guard let ageSeconds = lastExternalFrameAgeSeconds else {
      return .unavailable(.noAttachableFrame)
    }
    // A negative age is clock skew between the frame store and this decision,
    // not staleness — clamp to fresh rather than fail.
    let clampedAgeSeconds = max(0, ageSeconds)
    guard clampedAgeSeconds <= maxAgeSeconds else {
      return .unavailable(.frameTooStale(ageSeconds: Int(clampedAgeSeconds.rounded())))
    }
    return .lastExternalFrame
  }
}
