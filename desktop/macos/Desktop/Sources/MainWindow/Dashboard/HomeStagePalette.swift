import SwiftUI

/// Warm neutral palette for the redesigned Home stage, shared by
/// `DashboardPage` and the Dashboard section views.
///
/// `stageGlow` is deliberately neutral (INV-UI-1: accents stay white/neutral);
/// it was previously a violet literal that predated the brand ratchet.
enum HomeStagePalette {
  static let paper = Color(red: 0.018, green: 0.019, blue: 0.021)
  static let panel = Color(red: 0.045, green: 0.046, blue: 0.052)
  static let tile = Color(red: 0.078, green: 0.078, blue: 0.088)
  static let tileHover = Color(red: 0.11, green: 0.11, blue: 0.122)
  static let ink = Color(red: 0.94, green: 0.925, blue: 0.89)
  static let secondary = Color(red: 0.78, green: 0.765, blue: 0.725)
  static let muted = Color(red: 0.49, green: 0.47, blue: 0.43)
  static let faint = Color(red: 0.36, green: 0.35, blue: 0.33)
  static let hairline = Color(red: 0.155, green: 0.155, blue: 0.172)
  static let green = Color(red: 0.17, green: 0.78, blue: 0.38)
  static let stageGlow = Color(red: 0.92, green: 0.9, blue: 0.86)
  static let glow = stageGlow
}
