import SwiftUI

enum HomePalette {
  static let paper = Color(red: 0.018, green: 0.019, blue: 0.021)
  static let panel = Color(red: 0.045, green: 0.046, blue: 0.052)
  static let tile = Color(red: 0.078, green: 0.078, blue: 0.088)
  static let tileHover = Color(red: 0.108, green: 0.110, blue: 0.122)
  static let ink = Color(red: 0.97, green: 0.97, blue: 0.975)
  static let secondary = Color(red: 0.72, green: 0.73, blue: 0.75)
  static let muted = Color(red: 0.46, green: 0.47, blue: 0.50)
  static let faint = Color(red: 0.34, green: 0.35, blue: 0.37)
  static let hairline = Color(red: 0.155, green: 0.155, blue: 0.172)
  static let green = Color(red: 0.17, green: 0.78, blue: 0.38)
  // Neutral cool-grey key light (INV-UI-1 brand accent rules).
  static let stageGlow = Color(red: 0.72, green: 0.74, blue: 0.78)
  static let glow = stageGlow
}

enum HomeStatusState {
  case active
  case inactive
  case blocked

  var indicator: Color {
    switch self {
    case .active:
      return HomePalette.green
    case .inactive:
      return HomePalette.faint
    case .blocked:
      return Color(red: 1.0, green: 0.24, blue: 0.30)
    }
  }

  var text: String {
    switch self {
    case .active:
      return "On"
    case .inactive:
      return "Off"
    case .blocked:
      return "Blocked"
    }
  }

  var isActive: Bool {
    if case .active = self { return true }
    return false
  }

  var isBlocked: Bool {
    if case .blocked = self { return true }
    return false
  }
}
