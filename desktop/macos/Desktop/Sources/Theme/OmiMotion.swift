import AppKit
import SwiftUI

/// Reduced-motion-aware animation helpers. Use `.omiAnimation(_:value:)` and
/// `OmiMotion.withGated(_:_:)` instead of raw `.animation`/`withAnimation` so
/// the system "Reduce motion" accessibility setting disables movement app-wide.
package enum OmiMotion {
  package static var reduceMotion: Bool {
    NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
  }

  /// Returns `nil` (no animation) when the user asked for reduced motion.
  package static func gated(_ animation: Animation?) -> Animation? {
    reduceMotion ? nil : animation
  }

  /// Drop-in replacement for `withAnimation` that respects Reduce Motion.
  package static func withGated<Result>(
    _ animation: Animation? = .default,
    _ body: () throws -> Result
  ) rethrows -> Result {
    try withAnimation(gated(animation), body)
  }
}

package extension View {
  /// Drop-in replacement for `.animation(_:value:)` that respects Reduce Motion.
  func omiAnimation<V: Equatable>(_ animation: Animation?, value: V) -> some View {
    self.animation(OmiMotion.gated(animation), value: value)
  }
}
