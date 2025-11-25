import 'package:flutter/material.dart';
import 'package:omi/flavors.dart';

/// Brand color configuration for white-label support
/// Each flavor can define its own color scheme
class BrandColors {
  final Color primary;
  final Color secondary;
  final Color accent;
  final Color light;

  const BrandColors({
    required this.primary,
    required this.secondary,
    required this.accent,
    required this.light,
  });

  /// Get brand colors based on current flavor/environment
  static BrandColors getColorsForFlavor() {
    switch (F.env) {
      case Environment.prod:
        return _nootoPurple;
      case Environment.dev:
        return _nootoPurple; // Dev uses same colors as prod by default
      default:
        return _nootoPurple;
    }
  }

  // Nooto purple color scheme (default brand colors)
  static const BrandColors _nootoPurple = BrandColors(
    primary: Color(0xFF8B5CF6),    // Purple (Nooto brand color)
    secondary: Color(0xFFA78BFA),  // Lighter purple
    accent: Color(0xFF7C3AED),     // Darker purple
    light: Color(0xFFC4B5FD),      // Light purple
  );

  // Legacy Omi blue color scheme (kept for reference)
  // static const BrandColors _omiBlue = BrandColors(
  //   primary: Color(0xFF3B82F6),    // Blue (same as GPT button)
  //   secondary: Color(0xFF60A5FA),  // Lighter blue
  //   accent: Color(0xFF2563EB),     // Darker blue
  //   light: Color(0xFF93C5FD),      // Light blue
  // );

  // Example: Add more white-label configurations here
  // static const BrandColors _clientA = BrandColors(
  //   primary: Color(0xFF3B82F6),    // Blue
  //   secondary: Color(0xFF60A5FA),
  //   accent: Color(0xFF2563EB),
  //   light: Color(0xFF93C5FD),
  // );

  // static const BrandColors _clientB = BrandColors(
  //   primary: Color(0xFF10B981),    // Green
  //   secondary: Color(0xFF34D399),
  //   accent: Color(0xFF059669),
  //   light: Color(0xFF6EE7B7),
  // );

  /// Create a LinearGradient from primary to accent
  LinearGradient get gradient => LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [primary, accent],
      );

  /// Create a LinearGradient from secondary to light
  LinearGradient get lightGradient => LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [secondary, light],
      );
}
