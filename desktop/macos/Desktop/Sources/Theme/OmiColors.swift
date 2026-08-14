import SwiftUI

// The `OmiColors` palette that used to live here is gone. It was a hardcoded dark
// register (`backgroundPrimary` #0F0F0F, `textPrimary` #FFFFFF) from when the app
// painted its own near-black page. Surfaces now sit on the light-pinned glass panel
// (`InkGlass`), where every one of those values resolved to the panel's own colour —
// so a view still using it compiled, drew, and was blank.
//
// It is deleted rather than recoloured or aliased: a second palette that merely looks
// right is the shape someone reaches for by accident, and a silent invisible surface is
// the one failure a build cannot report. Use `Ink` (colour), `InkType` (type) and
// `PageGlass` / `GlassShell` / `NotchGlass` (surface vocabulary) instead.
//
// The hex initialisers below stay — they are a general `Color` convenience with callers
// across the app, unrelated to the retired palette.

extension Color {
  package init(hex: UInt, alpha: Double = 1.0) {
    self.init(
      .sRGB,
      red: Double((hex >> 16) & 0xFF) / 255.0,
      green: Double((hex >> 8) & 0xFF) / 255.0,
      blue: Double(hex & 0xFF) / 255.0,
      opacity: alpha
    )
  }

  /// Initialize from a hex string like "#6B7280" or "6B7280"
  package init?(hex hexString: String) {
    var cleanedString = hexString.trimmingCharacters(in: .whitespacesAndNewlines)
    cleanedString = cleanedString.replacingOccurrences(of: "#", with: "")

    guard cleanedString.count == 6,
      let hexValue = UInt(cleanedString, radix: 16)
    else {
      return nil
    }

    self.init(hex: hexValue)
  }
}
