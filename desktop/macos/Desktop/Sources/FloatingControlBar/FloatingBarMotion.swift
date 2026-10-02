import SwiftUI

/// The floating bar's named motion, in one place, until the app-wide tokens in
/// `Theme/OmiMotion.swift` absorb them. Every call still goes through `OmiMotion.withGated` /
/// `.omiAnimation`, so Reduce Motion is honored at the call site as before.
///
/// Springs the bar used before this file, and where each went:
///
/// | Was | Now |
/// |---|---|
/// | `.spring(0.24, 0.9)` ×4, `.spring(0.22, 0.9)` | `responseSurface` |
/// | `.spring(0.35, 0.82)` | `notice` |
/// | `.spring(0.28, 0.85)` | `inlineFeedback` |
/// | `.spring(0.18, 0.74)` | `logoHover` |
/// | `.spring(0.35, 0.75)` / `.spring(0.3, 1.0)` | `hoverMenuExpand` / `hoverMenuCollapse` (defined on the window, where source tests pin them) |
enum FloatingBarMotion {
  /// The Ask Omi answer surface appearing or leaving.
  static let responseSurface: Animation = .spring(response: 0.24, dampingFraction: 0.9)
  /// A notch notice card arriving or being replaced by the next one.
  static let notice: Animation = .spring(response: 0.35, dampingFraction: 0.82)
  /// A confirmation line inside a surface ("Share link copied").
  static let inlineFeedback: Animation = .spring(response: 0.28, dampingFraction: 0.85)
  /// The notch logo's hover pop: quick and slightly under-damped so it reads as a response.
  static let logoHover: Animation = .spring(response: 0.18, dampingFraction: 0.74)
  /// The hover menu (agent switcher) opening and closing.
  @MainActor static var hoverMenuExpand: Animation { FloatingControlBarWindow.notchHoverMenuExpandAnimation }
  @MainActor static var hoverMenuCollapse: Animation { FloatingControlBarWindow.notchHoverMenuCollapseAnimation }

  /// Hover chrome fading in or out (action rows, toggles).
  static let hoverFade: TimeInterval = 0.15
  /// A small state swap inside a surface (rating thanks replacing the rating row).
  static let stateFade: TimeInterval = 0.2
}
