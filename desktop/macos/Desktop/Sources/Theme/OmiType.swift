import SwiftUI

/// Type-size registers for the desktop app. Use with `scaledFont(size:weight:)`
/// (`.scaledFont(size: OmiType.body)`) instead of numeric literals so the
/// hierarchy stays trimodal and intentional. Off-register sizes (9, 12, 14,
/// 17, 18) round to the nearest register.
package enum OmiType {
  /// Display: onboarding hero titles.
  package static let hero: CGFloat = 40
  /// Page/section headers.
  package static let title: CGFloat = 28
  /// Card titles, prominent labels.
  package static let heading: CGFloat = 20
  /// Subheads, emphasized rows, primary buttons.
  package static let subheading: CGFloat = 15
  /// Default body text (macOS system body).
  package static let body: CGFloat = 13
  /// Secondary labels, captions.
  package static let caption: CGFloat = 11
  /// Micro badges, counters.
  package static let micro: CGFloat = 10
}
