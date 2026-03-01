import 'package:flutter/material.dart';

/// Semantic color tokens that resolve to light or dark values based on the active theme.
/// Use `context.appColors` to access these tokens throughout the app.
class AppColorTokens extends ThemeExtension<AppColorTokens> {
  // Backgrounds
  final Color backgroundPrimary;
  final Color backgroundSecondary;
  final Color backgroundTertiary;
  final Color backgroundQuaternary;

  // Text
  final Color textPrimary;
  final Color textSecondary;
  final Color textTertiary;
  final Color textQuaternary;

  // Cards
  final Color cardBackground;
  final Color secondaryCardBackground;

  // UI elements
  final Color dividerColor;
  final Color iconSecondary;
  final Color navBarBackground;
  final Color handleBar;

  // Semantic (same in both modes)
  final Color successColor;
  final Color warningColor;
  final Color errorColor;
  final Color infoColor;

  const AppColorTokens({
    required this.backgroundPrimary,
    required this.backgroundSecondary,
    required this.backgroundTertiary,
    required this.backgroundQuaternary,
    required this.textPrimary,
    required this.textSecondary,
    required this.textTertiary,
    required this.textQuaternary,
    required this.cardBackground,
    required this.secondaryCardBackground,
    required this.dividerColor,
    required this.iconSecondary,
    required this.navBarBackground,
    required this.handleBar,
    required this.successColor,
    required this.warningColor,
    required this.errorColor,
    required this.infoColor,
  });

  /// Dark mode preset
  static const dark = AppColorTokens(
    backgroundPrimary: Color(0xFF0F0F0F),
    backgroundSecondary: Color(0xFF1A1A1A),
    backgroundTertiary: Color(0xFF252525),
    backgroundQuaternary: Color(0xFF2A2A2A),
    textPrimary: Color(0xFFFFFFFF),
    textSecondary: Color(0xFFE5E5E5),
    textTertiary: Color(0xFFB0B0B0),
    textQuaternary: Color(0xFF888888),
    cardBackground: Color(0xFF1C1C1E),
    secondaryCardBackground: Color(0xFF2A2A2E),
    dividerColor: Color(0xFF3C3C43),
    iconSecondary: Color(0xFF8E8E93),
    navBarBackground: Color(0xFF0F0F0F),
    handleBar: Color(0xFF3C3C43),
    successColor: Color(0xFF10B981),
    warningColor: Color(0xFFF59E0B),
    errorColor: Color(0xFFEF4444),
    infoColor: Color(0xFF3B82F6),
  );

  /// Light mode preset
  static const light = AppColorTokens(
    backgroundPrimary: Color(0xFFFFFFFF),
    backgroundSecondary: Color(0xFFF2F2F7),
    backgroundTertiary: Color(0xFFFFFFFF),
    backgroundQuaternary: Color(0xFFE5E5EA),
    textPrimary: Color(0xFF000000),
    textSecondary: Color(0xDE3C3C43), // 87% opacity
    textTertiary: Color(0x993C3C43), // 60% opacity
    textQuaternary: Color(0x4D3C3C43), // 30% opacity
    cardBackground: Color(0xFFFFFFFF),
    secondaryCardBackground: Color(0xFFF2F2F7),
    dividerColor: Color(0xFFC6C6C8),
    iconSecondary: Color(0xFF8E8E93),
    navBarBackground: Color(0xFFF8F8F8),
    handleBar: Color(0xFFC6C6C8),
    successColor: Color(0xFF10B981),
    warningColor: Color(0xFFF59E0B),
    errorColor: Color(0xFFEF4444),
    infoColor: Color(0xFF3B82F6),
  );

  @override
  AppColorTokens copyWith({
    Color? backgroundPrimary,
    Color? backgroundSecondary,
    Color? backgroundTertiary,
    Color? backgroundQuaternary,
    Color? textPrimary,
    Color? textSecondary,
    Color? textTertiary,
    Color? textQuaternary,
    Color? cardBackground,
    Color? secondaryCardBackground,
    Color? dividerColor,
    Color? iconSecondary,
    Color? navBarBackground,
    Color? handleBar,
    Color? successColor,
    Color? warningColor,
    Color? errorColor,
    Color? infoColor,
  }) {
    return AppColorTokens(
      backgroundPrimary: backgroundPrimary ?? this.backgroundPrimary,
      backgroundSecondary: backgroundSecondary ?? this.backgroundSecondary,
      backgroundTertiary: backgroundTertiary ?? this.backgroundTertiary,
      backgroundQuaternary: backgroundQuaternary ?? this.backgroundQuaternary,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      textTertiary: textTertiary ?? this.textTertiary,
      textQuaternary: textQuaternary ?? this.textQuaternary,
      cardBackground: cardBackground ?? this.cardBackground,
      secondaryCardBackground: secondaryCardBackground ?? this.secondaryCardBackground,
      dividerColor: dividerColor ?? this.dividerColor,
      iconSecondary: iconSecondary ?? this.iconSecondary,
      navBarBackground: navBarBackground ?? this.navBarBackground,
      handleBar: handleBar ?? this.handleBar,
      successColor: successColor ?? this.successColor,
      warningColor: warningColor ?? this.warningColor,
      errorColor: errorColor ?? this.errorColor,
      infoColor: infoColor ?? this.infoColor,
    );
  }

  @override
  AppColorTokens lerp(ThemeExtension<AppColorTokens>? other, double t) {
    if (other is! AppColorTokens) return this;
    return AppColorTokens(
      backgroundPrimary: Color.lerp(backgroundPrimary, other.backgroundPrimary, t)!,
      backgroundSecondary: Color.lerp(backgroundSecondary, other.backgroundSecondary, t)!,
      backgroundTertiary: Color.lerp(backgroundTertiary, other.backgroundTertiary, t)!,
      backgroundQuaternary: Color.lerp(backgroundQuaternary, other.backgroundQuaternary, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      textTertiary: Color.lerp(textTertiary, other.textTertiary, t)!,
      textQuaternary: Color.lerp(textQuaternary, other.textQuaternary, t)!,
      cardBackground: Color.lerp(cardBackground, other.cardBackground, t)!,
      secondaryCardBackground: Color.lerp(secondaryCardBackground, other.secondaryCardBackground, t)!,
      dividerColor: Color.lerp(dividerColor, other.dividerColor, t)!,
      iconSecondary: Color.lerp(iconSecondary, other.iconSecondary, t)!,
      navBarBackground: Color.lerp(navBarBackground, other.navBarBackground, t)!,
      handleBar: Color.lerp(handleBar, other.handleBar, t)!,
      successColor: Color.lerp(successColor, other.successColor, t)!,
      warningColor: Color.lerp(warningColor, other.warningColor, t)!,
      errorColor: Color.lerp(errorColor, other.errorColor, t)!,
      infoColor: Color.lerp(infoColor, other.infoColor, t)!,
    );
  }
}

/// Extension to easily access color tokens from BuildContext
extension AppColorTokensExtension on BuildContext {
  AppColorTokens get appColors => Theme.of(this).extension<AppColorTokens>() ?? AppColorTokens.dark;
}
