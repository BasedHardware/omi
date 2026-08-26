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
  static let hairline = Ink.hairline
  static let green = Ink.listeningGreen

  /// Home's emphasis colour — what a hover, a focus ring, or a lit-up glyph moves *toward*.
  ///
  /// It was `Ink.glow` (fixed white), which is the dark page's answer: on a near-black canvas
  /// "emphasised" means brighter. This page has no canvas of its own any more, so emphasis moves
  /// the other way and every one of those hovers, rings and glyphs was drawing white onto light
  /// glass — present in the layout, invisible on screen. `Ink.primary` is the same idea stated for
  /// this ground, and being an alpha on `labelColor` it lands in the same wash vocabulary
  /// (`rowFill` 0.045 · `wash` 0.06 · `hairline` 0.22) the rest of the glass chrome is built from.
  /// Neutral either way, never a brand hue (`INV-UI-1`).
  static let stageGlow = Ink.primary
  static let glow = stageGlow
}

/// The Home ask bar's action button, as colour rather than as statements inside a view.
///
/// A value for the reason `OmiToggleStyle.trackFill` is one: the bug these replaced was a *filled*
/// control whose fill and label were picked for a dark page — a white disc with a black arrow, a
/// white "Connect" capsule with black text — which on light glass is a disc you cannot see wearing
/// a glyph you can. That failure is a contrast ratio, so it belongs somewhere a hermetic test can
/// measure it (`GlassLegibilityTests`) instead of somewhere only a screenshot can.
///
/// The primary action is the ink itself: on this ground the heaviest thing available *is* the
/// label colour, and a stadium of it under `Ink.surface` type is the highest-contrast pairing the
/// palette can make without reaching for a hue.
enum HomeAskBarPalette {
  /// Send / active-Connect: a filled ink capsule.
  static let primaryFill = Ink.primary
  /// The glyph or label on `primaryFill` — the panel's own colour, so the pairing inverts cleanly.
  static let primaryLabel = Ink.surface

  /// Stop, and Connect at rest: a wash rather than a fill, because neither is the page's one
  /// primary action and a second filled capsule beside Send reads as two.
  static func secondaryFill(isHovering: Bool) -> Color {
    isHovering ? Ink.rowFillHover : Ink.rowFill
  }

  /// The label on `secondaryFill`.
  static let secondaryLabel = Ink.primary

  /// The bar's own well, and the one visible difference between resting and engaged.
  ///
  /// Stated as two washes rather than one wash at two alphas: the old pair differed by 8% of a
  /// 4.5% alpha — about 0.4/255 on the composite — which is a focus state nobody can see.
  static func wellFill(isEngaged: Bool) -> Color {
    isEngaged ? Ink.rowFillHover : Ink.rowFill
  }

  /// The bar's outline. `hairline` when focused so the ring is a real edge, `separator` at rest.
  static func wellStroke(isFocused: Bool, isDropTargeted: Bool) -> Color {
    if isDropTargeted { return Ink.accent }
    return isFocused ? Ink.hairline : Ink.separator
  }
}

enum HomeStatusState: Equatable {
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
