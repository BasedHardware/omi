import SwiftUI

/// Spacing ladder for the desktop app. Use these instead of numeric padding /
/// spacing literals so rhythm stays consistent across surfaces.
/// Off-ladder values (10, 14, 18, 22, 26, 28, 36) round to the nearest step.
package enum OmiSpacing {
  package static let hairline: CGFloat = 2
  package static let xxs: CGFloat = 4
  package static let xs: CGFloat = 6
  package static let sm: CGFloat = 8
  package static let md: CGFloat = 12
  package static let lg: CGFloat = 16
  package static let xl: CGFloat = 20
  package static let xxl: CGFloat = 24
  package static let section: CGFloat = 32
  package static let page: CGFloat = 40
}
