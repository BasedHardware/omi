import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppColors {
  static const Color backgroundPrimary = Color(0xFF0F0F0F);
  static const Color backgroundSecondary = Color(0xFF1A1A1A);
  static const Color backgroundTertiary = Color(0xFF252525);
  static const Color backgroundQuaternary = Color(0xFF2A2A2A);

  static const Color textPrimary = Color(0xFFFFFFFF);
  static const Color textSecondary = Color(0xFFE5E5E5);
  static const Color textTertiary = Color(0xFFB0B0B0);
  static const Color textQuaternary = Color(0xFF888888);

  static const Color brandPrimary = Color(0xFF3B82F6);
  static const Color brandAccent = Color(0xFF2563EB);
  static const Color brandLight = Color(0xFF93C5FD);

  static const Color successColor = Color(0xFF10B981);
  static const Color warningColor = Color(0xFFF59E0B);
  static const Color errorColor = Color(0xFFEF4444);
}

class AppStyles {
  static const double spacingXS = 4.0;
  static const double spacingS = 8.0;
  static const double spacingM = 12.0;
  static const double spacingL = 16.0;
  static const double spacingXL = 24.0;
  static const double spacingXXL = 32.0;

  static const double radiusSmall = 6.0;
  static const double radiusMedium = 8.0;
  static const double radiusLarge = 12.0;
  static const double radiusXLarge = 20.0;
  static const double radiusPill = 999.0;

  static const double touchTargetMinimum = 44.0;
}

/// Brand emphasis serif used for taglines and the wordmark.
/// Matches `desktop-v2`'s "font-serif italic" treatment.
TextStyle brandSerif({
  double fontSize = 16,
  FontWeight fontWeight = FontWeight.w500,
  FontStyle fontStyle = FontStyle.italic,
  Color color = AppColors.textPrimary,
  double? height,
}) {
  return GoogleFonts.playfairDisplay(
    fontSize: fontSize,
    fontWeight: fontWeight,
    fontStyle: fontStyle,
    color: color,
    height: height,
  );
}

ThemeData buildAppTheme() {
  return ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: AppColors.backgroundPrimary,
    colorScheme: const ColorScheme.dark(
      primary: AppColors.brandPrimary,
      secondary: AppColors.brandAccent,
      surface: AppColors.backgroundSecondary,
      error: AppColors.errorColor,
    ),
    textTheme: const TextTheme(
      displayLarge: TextStyle(fontSize: 36, fontWeight: FontWeight.w600, color: AppColors.textPrimary, height: 1.15),
      headlineMedium: TextStyle(fontSize: 22, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
      bodyLarge: TextStyle(fontSize: 16, color: AppColors.textSecondary, height: 1.4),
      bodyMedium: TextStyle(fontSize: 14, color: AppColors.textSecondary, height: 1.4),
      labelLarge: TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: AppColors.textPrimary),
    ),
    iconTheme: const IconThemeData(color: AppColors.textPrimary),
    useMaterial3: true,
  );
}
