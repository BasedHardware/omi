import SwiftUI

/// Light-mode "warm paper" design system for the macOS redesign.
///
/// Ported 1:1 from the mockup's `design-system.css`. The palette is deliberately
/// **monochrome ink** — the accent is near-black ink (`ink`), never purple, never a
/// colored brand hue. Color is reserved for semantic status only: `live` green,
/// `warn` orange, `danger` red.
///
/// These are explicit colors (not system-semantic), so redesigned surfaces render
/// as warm-paper light even while the host window is still `.darkAqua`.
enum Ink {
  // MARK: Surfaces (light — warm paper)
  static let canvas = Color(hex: 0xF4F2ED)  // app backdrop
  static let soft = Color(hex: 0xFAFAF7)  // bars / rails
  static let surface = Color(hex: 0xFFFFFF)  // cards
  static let surface2 = Color(hex: 0xF6F5F1)  // recessed / hover

  // MARK: Text ladder
  static let ink = Color(hex: 0x201F1A)  // strongest text
  static let body = Color(hex: 0x55534C)
  static let muted = Color(hex: 0x86847C)  // AI-written text
  static let faint = Color(hex: 0xA9A79E)

  // MARK: Hairlines
  static let hair = Color(hex: 0xE4E2DB)
  static let hair2 = Color(hex: 0xD8D6CE)

  // MARK: Accent — monochrome ink
  static let accent = Color(hex: 0x201F1A)
  static let accentStrong = Color(hex: 0x000000)
  static let accentInk = Color(hex: 0xFFFFFF)  // text/icon that sits on an accent fill
  static let accentTint = Color(hex: 0x201F1A, alpha: 0.10)

  // MARK: Semantic status (used sparingly)
  static let live = Color(hex: 0x2CC66B)  // capture / listening / granted / held
  static let warn = Color(hex: 0xE8913A)  // needs-you / due today
  static let danger = Color(hex: 0xE5544B)  // destructive
  static let warnText = Color(hex: 0xB8541A)
  static let sentText = Color(hex: 0x1F8A4C)

  // MARK: Shadows
  static let shadow = Color(hex: 0x1E1C16, alpha: 0.10)

  // MARK: Avatar / icon fills (brand-derived, never purple)
  static let fillSlate = Color(hex: 0x5B6472)
  static let fillTeal = Color(hex: 0x2F7D78)
  static let fillBlue = Color(hex: 0x3B6EA5)
  static let fillClay = Color(hex: 0xA5623B)
  static let fillMoss = Color(hex: 0x5C7A3F)
  static let fillInk = Color(hex: 0x3A3934)

  static let avatarFills: [Color] = [fillSlate, fillTeal, fillBlue, fillClay, fillMoss, fillInk]

  /// Deterministic avatar color for a name/handle.
  static func avatarFill(for seed: String) -> Color {
    guard !seed.isEmpty else { return fillInk }
    let hash = seed.unicodeScalars.reduce(0) { ($0 &* 31 &+ Int($1.value)) & 0x7FFF_FFFF }
    return avatarFills[hash % avatarFills.count]
  }
}

/// Spacing scale (4px base) and corner radii from the mockup.
enum InkSpace {
  static let s1: CGFloat = 4
  static let s2: CGFloat = 8
  static let s3: CGFloat = 12
  static let s4: CGFloat = 16
  static let s5: CGFloat = 24
  static let s6: CGFloat = 32
  static let s7: CGFloat = 48
  static let s8: CGFloat = 80
}

enum InkRadius {
  static let btn: CGFloat = 999  // buttons are fully pill-soft in the final mockup
  static let card: CGFloat = 14
  static let tile: CGFloat = 12
  static let next: CGFloat = 18
  static let pill: CGFloat = 999
  static let window: CGFloat = 12
}
