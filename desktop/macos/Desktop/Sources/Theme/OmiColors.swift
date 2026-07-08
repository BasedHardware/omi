import SwiftUI

/// Shared dark palette for the native macOS app.
/// Keep this aligned with the stronger parts of the older Flutter desktop styling:
/// neutral dark surfaces, restrained borders, and a purple accent without neon overload.
package enum OmiColors {
  // MARK: - Background Colors
  package static let backgroundPrimary = Color(hex: 0x0F0F0F)
  package static let backgroundSecondary = Color(hex: 0x1A1A1A)
  package static let backgroundTertiary = Color(hex: 0x252525)
  package static let backgroundQuaternary = Color(hex: 0x35343B)
  package static let backgroundRaised = Color(hex: 0x1F1F25)

  // MARK: - Border Colors
  package static let border = Color(hex: 0x3A3940)

  // MARK: - Accent System
  package static let purplePrimary = Color(hex: 0x8B5CF6)
  package static let purpleSecondary = Color(hex: 0xA855F7)
  package static let purpleAccent = Color(hex: 0x7C3AED)
  package static let purpleLight = Color(hex: 0xD946EF)

  // MARK: - Text Colors
  package static let textPrimary = Color(hex: 0xFFFFFF)
  package static let textSecondary = Color(hex: 0xE5E5E5)
  package static let textTertiary = Color(hex: 0xB0B0B0)
  package static let textQuaternary = Color(hex: 0x888888)

  // MARK: - Status Colors
  package static let success = Color(hex: 0x10B981)  // Green
  package static let warning = Color(hex: 0xF59E0B)  // Amber
  package static let error = Color(hex: 0xEF4444)  // Red
  package static let info = Color(hex: 0x3B82F6)  // Blue
  package static let amber = Color(hex: 0xF59E0B)  // Same as warning, for starred items

  // MARK: - Mac Window Button Colors
  package static let windowButtonClose = Color(hex: 0xFF5F57)
  package static let windowButtonMinimize = Color(hex: 0xFFBD2E)
  package static let windowButtonMaximize = Color(hex: 0x28CA42)

  // MARK: - Speaker Colors (for transcript bubbles)
  package static let speakerColors: [Color] = [
    Color(hex: 0x2D3748),  // Dark blue-gray
    Color(hex: 0x1E3A5F),  // Navy
    Color(hex: 0x2D4A3E),  // Dark teal
    Color(hex: 0x4A3728),  // Dark brown
    Color(hex: 0x3D2E4A),  // Dark purple
    Color(hex: 0x4A3A2D),  // Dark amber
  ]

  /// User bubble color: richer than the page chrome, softer than a flat primary fill.
  package static let userBubble = Color(hex: 0x43389F)

  // MARK: - Gradients
  package static let purpleGradient = LinearGradient(
    colors: [purplePrimary, purpleAccent],
    startPoint: .topLeading,
    endPoint: .bottomTrailing
  )

  package static let purpleLightGradient = LinearGradient(
    colors: [purpleSecondary, purpleLight],
    startPoint: .topLeading,
    endPoint: .bottomTrailing
  )
}

// MARK: - Color Extension for Hex
package extension Color {
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
  init?(hex hexString: String) {
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
