import OmiTheme
import SwiftUI

/// Home's token register, mapped onto the glass vocabulary.
///
/// These were hand-mixed near-blacks for a dark page. On the light-pinned glass panel
/// every one of them was the panel's own colour — the surface compiled and drew, and was
/// blank. Mapping the register (rather than its ~133 call sites) moves the whole page and
/// keeps `DashboardPage.swift` byte-for-byte at its line-count baseline.
///
/// Glass carries two type rungs, so `muted` and `faint` both resolve to `Ink.secondary`
/// rather than inventing a third that fails contrast on this ground.
enum HomePalette {
  /// The page paints nothing: the glass panel owns the one ground in the window.
  static let paper = Color.clear
  static let panel = Ink.rowFill
  static let tile = Ink.rowFill
  static let tileHover = Ink.rowFillHover
  static let ink = Ink.primary
  static let secondary = Ink.secondary
  static let muted = Ink.secondary
  static let faint = Ink.secondary
  static let hairline = Ink.separator
  static let green = Ink.listeningGreen
  /// Neutral key light, never a brand hue (`INV-UI-1`).
  static let stageGlow = Ink.glow
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
      return Ink.errorRed
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
