import 'package:flutter/material.dart';

/// App-wide color constants
/// Use these instead of Colors.deepPurple or Colors.purpleAccent
class AppColors {
  // Primary brand color (blue, matching GPT button)
  static const Color primary = Color(0xFF3B82F6);
  static const Color primaryLight = Color(0xFF60A5FA);
  static const Color primaryDark = Color(0xFF2563EB);

  // For backward compatibility with code that used deepPurple
  // These now point to the blue color
  static const Color deepPurple = primary;
  static const Color deepPurpleShade100 = Color(0xFF93C5FD);
  static const Color deepPurpleShade200 = primaryLight;
  static const Color deepPurpleShade300 = primary;
  static const Color purpleAccent = primary;
  static const Color purpleAccentShade100 = primaryLight;
}
