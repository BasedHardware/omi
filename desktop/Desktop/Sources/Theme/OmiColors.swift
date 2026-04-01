import SwiftUI

/// Shared dark palette for the native macOS app.
/// Keep this aligned with the stronger parts of the older Flutter desktop styling:
/// neutral dark surfaces, restrained borders, and a purple accent without neon overload.
enum OmiColors {
  // MARK: - Background Colors
  static let backgroundPrimary = Color(hex: 0x0F0F0F)
  static let backgroundSecondary = Color(hex: 0x1A1A1A)
  static let backgroundTertiary = Color(hex: 0x252525)
  static let backgroundQuaternary = Color(hex: 0x35343B)
  static let backgroundRaised = Color(hex: 0x1F1F25)

  // MARK: - Border Colors
  static let border = Color(hex: 0x3A3940)

  // MARK: - Accent System
  static let purplePrimary = Color(hex: 0x8B5CF6)
  static let purpleSecondary = Color(hex: 0xA855F7)
  static let purpleAccent = Color(hex: 0x7C3AED)
  static let purpleLight = Color(hex: 0xD946EF)

  // MARK: - Text Colors
  static let textPrimary = Color(hex: 0xFFFFFF)
  static let textSecondary = Color(hex: 0xE5E5E5)
  static let textTertiary = Color(hex: 0xB0B0B0)
  static let textQuaternary = Color(hex: 0x888888)

  // MARK: - Status Colors
  static let success = Color(hex: 0x10B981)  // Green
  static let warning = Color(hex: 0xF59E0B)  // Amber
  static let error = Color(hex: 0xEF4444)  // Red
  static let info = Color(hex: 0x3B82F6)  // Blue
  static let amber = Color(hex: 0xF59E0B)  // Same as warning, for starred items

  // MARK: - Mac Window Button Colors
  static let windowButtonClose = Color(hex: 0xFF5F57)
  static let windowButtonMinimize = Color(hex: 0xFFBD2E)
  static let windowButtonMaximize = Color(hex: 0x28CA42)

  // MARK: - Speaker Colors (for transcript bubbles)
  static let speakerColors: [Color] = [
    Color(hex: 0x2D3748),  // Dark blue-gray
    Color(hex: 0x1E3A5F),  // Navy
    Color(hex: 0x2D4A3E),  // Dark teal
    Color(hex: 0x4A3728),  // Dark brown
    Color(hex: 0x3D2E4A),  // Dark purple
    Color(hex: 0x4A3A2D),  // Dark amber
  ]

  /// User bubble color: richer than the page chrome, softer than a flat primary fill.
  static let userBubble = Color(hex: 0x43389F)

  // MARK: - Gradients
  static let purpleGradient = LinearGradient(
    colors: [purplePrimary, purpleAccent],
    startPoint: .topLeading,
    endPoint: .bottomTrailing
  )

  static let purpleLightGradient = LinearGradient(
    colors: [purpleSecondary, purpleLight],
    startPoint: .topLeading,
    endPoint: .bottomTrailing
  )
}

// MARK: - Color Extension for Hex
extension Color {
  init(hex: UInt, alpha: Double = 1.0) {
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
