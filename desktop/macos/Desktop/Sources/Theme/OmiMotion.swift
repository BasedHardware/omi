import AppKit
import SwiftUI

/// The app's three motion tokens. Pick by what moves, not by taste:
///
/// | Token | Curve | For |
/// |---|---|---|
/// | `quick` | ease-out 0.12 s | a control answering a press, hover or toggle; Esc and pill switches |
/// | `standard` | ease-in-out 0.24 s | content changing in place: a row, a panel, a list, a scroll, a step |
/// | `emphasized` | spring 0.35 / 0.86 | a surface arriving or leaving: a sheet, a card, a toast |
///
/// `standard` is `InkMotion.stepTransition`, so an onboarding step and a page change share one tempo.
/// `InkMotion` stays the first-run duration table (word reveal, finale glow…); `InkReduceMotion` and
/// `OmiMotion` read the same setting, and new code uses these tokens through `OmiMotion`.
package enum OmiMotionToken: CaseIterable, Sendable {
  case quick
  case standard
  case emphasized

  /// The curve before Reduce Motion is applied. Read it through `OmiMotion.animation(_:)`.
  package var curve: Animation {
    switch self {
    case .quick: return .easeOut(duration: 0.12)
    case .standard: return .easeInOut(duration: InkMotion.stepTransition)
    case .emphasized: return .spring(response: 0.35, dampingFraction: 0.86)
    }
  }
}

/// Reduced-motion-aware animation helpers. Use `.omiAnimation(_:value:)` and
/// `OmiMotion.perform(_:_:)` / `OmiMotion.withGated(_:_:)` instead of raw `.animation`/`withAnimation`
/// so the system "Reduce motion" accessibility setting disables movement app-wide.
package enum OmiMotion {
  /// The one reading of the setting, shared with `InkReduceMotion`.
  package static var reduceMotion: Bool {
    InkReduceMotion.isEnabled
  }

  /// A token's animation, or `nil` (apply the change instantly) under Reduce Motion.
  package static func animation(_ token: OmiMotionToken) -> Animation? {
    gated(token.curve)
  }

  /// Returns `nil` (no animation) when the user asked for reduced motion.
  package static func gated(_ animation: Animation?) -> Animation? {
    reduceMotion ? nil : animation
  }

  /// `withAnimation` with a token, or a straight mutation under Reduce Motion.
  package static func perform<Result>(_ token: OmiMotionToken, _ body: () throws -> Result) rethrows -> Result {
    try withAnimation(animation(token), body)
  }

  /// Drop-in replacement for `withAnimation` that respects Reduce Motion.
  package static func withGated<Result>(
    _ animation: Animation? = .default,
    _ body: () throws -> Result
  ) rethrows -> Result {
    try withAnimation(gated(animation), body)
  }
}

extension View {
  /// Drop-in replacement for `.animation(_:value:)` that respects Reduce Motion.
  package func omiAnimation<V: Equatable>(_ animation: Animation?, value: V) -> some View {
    self.animation(OmiMotion.gated(animation), value: value)
  }

  /// `.animation(_:value:)` with a motion token, off under Reduce Motion.
  package func omiAnimation<V: Equatable>(_ token: OmiMotionToken, value: V) -> some View {
    self.animation(OmiMotion.animation(token), value: value)
  }
}
