import Combine
import SwiftUI

// MARK: - Second Brain design tokens
//
// Faithful port of the design handoff's `:root` (dark) and `.light` CSS custom
// properties. Strictly monochrome — the ONLY "accent" is the inverted-ink button.
// The notch pill stays black glass in BOTH themes (see `SBTheme.pillBackground`).
//
// Usage in a view:
//   @Environment(\.sbTheme) private var sb
//   ...
//   .foregroundStyle(sb.ink(.w85))
//   .background(sb.panel)

package enum SBThemeMode: String, CaseIterable, Sendable {
  case dark
  case light
}

/// Named ink/fill alpha tokens from the design's white-alpha scale.
/// Each resolves to a specific alpha in dark (over white) and light (over ink base 26,28,34).
package enum SBInk: Sendable {
  case w9, w88, w85, w8, w75, w7, w6, w55, w5, w45, w42, w4, w38, w35, w32, w3, w28, w25
  case w18, w16, w15, w14, w12, w11, w1, w09, w08, w07, w06, w05, w04, w02

  /// (darkAlpha over white, lightAlpha over ink base 26,28,34) — verbatim from the design.
  var alphas: (dark: Double, light: Double) {
    switch self {
    case .w9: return (0.90, 0.95)
    case .w88: return (0.88, 0.95)
    case .w85: return (0.85, 0.95)
    case .w8: return (0.80, 0.90)
    case .w75: return (0.75, 0.85)
    case .w7: return (0.70, 0.80)
    case .w6: return (0.60, 0.70)
    case .w55: return (0.55, 0.65)
    case .w5: return (0.50, 0.60)
    case .w45: return (0.45, 0.55)
    case .w42: return (0.42, 0.52)
    case .w4: return (0.40, 0.50)
    case .w38: return (0.38, 0.48)
    case .w35: return (0.35, 0.45)
    case .w32: return (0.32, 0.42)
    case .w3: return (0.30, 0.40)
    case .w28: return (0.28, 0.38)
    case .w25: return (0.25, 0.35)
    case .w18: return (0.18, 0.28)
    case .w16: return (0.16, 0.26)
    case .w15: return (0.15, 0.25)
    case .w14: return (0.14, 0.24)
    case .w12: return (0.12, 0.17)
    case .w11: return (0.11, 0.16)
    case .w1: return (0.10, 0.15)
    case .w09: return (0.09, 0.14)
    case .w08: return (0.08, 0.13)
    case .w07: return (0.07, 0.12)
    case .w06: return (0.06, 0.11)
    case .w05: return (0.05, 0.10)
    case .w04: return (0.04, 0.09)
    case .w02: return (0.02, 0.07)
    }
  }
}

/// Resolved palette for a theme mode. A value type — cheap to pass in the environment.
package struct SBTheme: Equatable, Sendable {
  package let mode: SBThemeMode

  package init(_ mode: SBThemeMode) { self.mode = mode }

  package var isLight: Bool { mode == .light }

  // Ink base the alpha scale is layered on.
  private var inkBase: Color {
    isLight ? Color(hex: 0x1A1C22) : Color(hex: 0xFFFFFF)
  }

  /// Ink/fill token at the design's alpha for the current theme.
  package func ink(_ token: SBInk) -> Color {
    let a = token.alphas
    return inkBase.opacity(isLight ? a.light : a.dark)
  }

  // MARK: Solid inks
  /// Primary text / logo tint.
  package var ink: Color { isLight ? Color(hex: 0x1D1D1F) : Color(hex: 0xFFFFFF) }
  /// Inverted ink — the ONLY accent (button fills / their text-on-ink).
  package var inkInverted: Color { isLight ? Color(hex: 0xFFFFFF) : Color(hex: 0x0D0D0D) }

  // MARK: Surfaces
  package var background: Color { isLight ? Color(hex: 0xF5F5F7) : Color(hex: 0x0E0F11) }
  /// Glass panel fill (used with a blur material behind it).
  package var panel: Color { isLight ? Color(hex: 0xFFFFFF).opacity(0.82) : Color(hex: 0x0F0F11).opacity(0.72) }
  /// Opaque raised panel (palette / popovers).
  package var panel2: Color { isLight ? Color(hex: 0xFFFFFF).opacity(0.98) : Color(hex: 0x12121A).opacity(0.98) }

  // MARK: Notch pill — BLACK GLASS IN BOTH THEMES (final design decision)
  package var pillBackground: Color { isLight ? Color(hex: 0x0A0A0C).opacity(0.85) : Color(hex: 0x0A0A0C).opacity(0.80) }
  /// Ink scale *inside* the pill is always the dark (white-on-black) scale.
  package func pillInk(_ token: SBInk) -> Color { Color.white.opacity(token.alphas.dark) }
  package var pillInkSolid: Color { .white }
  package var pillInkInverted: Color { Color(hex: 0x0D0D0D) }

  // MARK: Wallpaper — ridgeline hills + horizon glow
  package var hillA: Color { isLight ? Color(hex: 0xE9E9EE) : Color(hex: 0x1B1D22) }
  package var hillA2: Color { isLight ? Color(hex: 0xF2F2F5) : Color(hex: 0x101114) }
  package var hillB: Color { isLight ? Color(hex: 0xE1E1E7) : Color(hex: 0x17181D) }
  package var hillB2: Color { isLight ? Color(hex: 0xECECF0) : Color(hex: 0x0E0F12) }
  package var hillC: Color { isLight ? Color(hex: 0xD9D9E0) : Color(hex: 0x131418) }
  package var hillC2: Color { isLight ? Color(hex: 0xE6E6EB) : Color(hex: 0x0D0E10) }
  package var glowTint: Color { isLight ? Color.white.opacity(0.90) : Color(hex: 0xC8D2E1).opacity(0.09) }
}

// MARK: - Environment plumbing

private struct SBThemeKey: EnvironmentKey {
  static let defaultValue = SBTheme(.dark)
}

extension EnvironmentValues {
  package var sbTheme: SBTheme {
    get { self[SBThemeKey.self] }
    set { self[SBThemeKey.self] = newValue }
  }
}

/// App-wide theme selection, persisted. Toggled by the menu-bar ◐ control.
@MainActor
package final class SBThemeManager: ObservableObject {
  package static let shared = SBThemeManager()
  private let key = "sbThemeMode"

  @Published package var mode: SBThemeMode {
    didSet { UserDefaults.standard.set(mode.rawValue, forKey: key) }
  }

  private init() {
    let raw = UserDefaults.standard.string(forKey: key)
    self.mode = raw.flatMap(SBThemeMode.init(rawValue:)) ?? .dark
  }

  package var theme: SBTheme { SBTheme(mode) }

  package func toggle() { mode = (mode == .dark) ? .light : .dark }
}

/// Injects the current SBTheme + matching color scheme into the environment.
package struct SBThemeEnvironmentModifier: ViewModifier {
  @ObservedObject private var manager = SBThemeManager.shared

  package init() {}

  package func body(content: Content) -> some View {
    content
      .environment(\.sbTheme, manager.theme)
      .preferredColorScheme(manager.mode == .light ? .light : .dark)
  }
}

extension View {
  /// Apply at the app root to drive the Second Brain theme.
  package func withSecondBrainTheme() -> some View { modifier(SBThemeEnvironmentModifier()) }
}

// MARK: - Motion (verbatim timings from the design)

package enum SBMotion {
  /// Standard state change: single ease-out, 180–240ms.
  package static let standard = Animation.timingCurve(0.3, 0.7, 0.3, 1.0, duration: 0.22)
  /// Notch pill expansions: 240ms ease-out.
  package static let pill = Animation.timingCurve(0.3, 0.7, 0.3, 1.0, duration: 0.24)
  /// Chat/message entrance: fade + translateY, ~280ms.
  package static let message = Animation.easeOut(duration: 0.28)
  /// Toggle knob slide.
  package static let toggle = Animation.easeOut(duration: 0.18)

  // Continuous loops (the only animations allowed to repeat).
  /// Logo spin — 2.4s linear, ONLY while Omi is actively working.
  package static let logoSpin = Animation.linear(duration: 2.4).repeatForever(autoreverses: false)
  /// Sign-in / hero breathing — 4s.
  package static let breathe = Animation.easeInOut(duration: 4.0).repeatForever(autoreverses: true)
}
