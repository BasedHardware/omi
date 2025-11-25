import 'package:flutter/material.dart';
import 'package:omi/theme/brand_colors.dart';

/// App color palette - provides a consistent color system across the app
/// These colors are independent of brand colors and represent the UI foundation
class AppColors {
  // Backgrounds
  static const Color backgroundPrimary = Color(0xFF0F0F0F); // Deep black
  static const Color backgroundSecondary = Color(0xFF1A1A1A); // Elevated surface
  static const Color backgroundTertiary = Color(0xFF252525); // Cards and components
  static const Color backgroundQuaternary = Color(0xFF2A2A2A); // Hover states

  // Text colors
  static const Color textPrimary = Color(0xFFFFFFFF); // Pure white for headers
  static const Color textSecondary = Color(0xFFE5E5E5); // Light gray for body
  static const Color textTertiary = Color(0xFFB0B0B0); // Medium gray for meta
  static const Color textQuaternary = Color(0xFF888888); // Dark gray for disabled

  // Semantic colors
  static const Color successColor = Color(0xFF10B981); // Green
  static const Color warningColor = Color(0xFFF59E0B); // Amber
  static const Color errorColor = Color(0xFFEF4444); // Red
  static const Color infoColor = Color(0xFF3B82F6); // Blue
}

/// Provides theme configuration with white-label color support
class AppTheme {
  final BrandColors brandColors;

  const AppTheme({required this.brandColors});

  /// Create ThemeData for the app with brand colors
  ThemeData get themeData => ThemeData(
        useMaterial3: false,
        colorScheme: ColorScheme.dark(
          primary: Colors.black, // Keep primary as black for backgrounds
          secondary: brandColors.primary, // Use brand color for accents
          tertiary: brandColors.accent,
          surface: AppColors.backgroundTertiary,
          onPrimary: AppColors.textPrimary,
          onSecondary: AppColors.textPrimary,
          onSurface: AppColors.textPrimary,
          error: AppColors.errorColor,
        ),
        scaffoldBackgroundColor: AppColors.backgroundPrimary,
        cardColor: AppColors.backgroundTertiary,
        dividerColor: AppColors.backgroundQuaternary,
        brightness: Brightness.dark,
        textTheme: const TextTheme(
          displayLarge: TextStyle(
            fontSize: 57,
            fontWeight: FontWeight.w800,
            color: AppColors.textPrimary,
          ),
          displayMedium: TextStyle(
            fontSize: 45,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          ),
          displaySmall: TextStyle(
            fontSize: 36,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
          headlineLarge: TextStyle(
            fontSize: 32,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
          headlineMedium: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.w600,
            color: AppColors.textPrimary,
          ),
          headlineSmall: TextStyle(
            fontSize: 24,
            fontWeight: FontWeight.w500,
            color: AppColors.textPrimary,
          ),
          titleLarge: TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.w500,
            color: AppColors.textPrimary,
          ),
          titleMedium: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w500,
            color: AppColors.textPrimary,
          ),
          titleSmall: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w500,
            color: AppColors.textSecondary,
          ),
          bodyLarge: TextStyle(
            fontSize: 16,
            color: AppColors.textSecondary,
          ),
          bodyMedium: TextStyle(
            fontSize: 14,
            color: AppColors.textSecondary,
          ),
          bodySmall: TextStyle(
            fontSize: 12,
            color: AppColors.textTertiary,
          ),
          labelLarge: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w500,
            color: AppColors.textPrimary,
          ),
        ),
      );

  /// Background gradient for the app
  LinearGradient get backgroundGradient => const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          AppColors.backgroundPrimary,
          AppColors.backgroundSecondary,
          AppColors.backgroundPrimary,
        ],
      );
}
