import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

/// Legacy style constants. Superseded by the tokens in `lib/ui/omi_tokens.dart`: use `OmiColors`,
/// `OmiType`, `OmiRadius` and `OmiSpacing` in new code, and migrate a file off `AppStyles` when you
/// touch it. The colours and text styles point at the v2 tokens (and follow light and dark), so
/// screens still on AppStyles restyle with the rest of the app.
class AppStyles {
  // Text Styles
  static TextStyle get title => TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: OmiColors.textPrimary);

  static TextStyle get subtitle => TextStyle(fontSize: 16, fontWeight: FontWeight.w500, color: OmiColors.textPrimary);

  static TextStyle get body => TextStyle(fontSize: 15, height: 1.4, color: OmiColors.textPrimary);

  static TextStyle get caption => TextStyle(fontSize: 14, color: OmiColors.textSecondary);

  static TextStyle get small => TextStyle(fontSize: 12, color: OmiColors.textSecondary);

  static TextStyle get label => TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: OmiColors.textSecondary);

  // Colors
  static Color get backgroundPrimary => OmiColors.surface0;
  static Color get backgroundSecondary => OmiColors.surface1;
  static Color get backgroundTertiary => OmiColors.surface2;

  static Color get textPrimary => OmiColors.textPrimary;
  static Color get textSecondary => OmiColors.textSecondary;
  static Color get textTertiary => OmiColors.textTertiary;

  static const Color accent = Colors.blue;
  static Color get error => OmiColors.danger;
  static Color get success => OmiColors.success;

  // Spacing
  static const double spacingXS = 4.0;
  static const double spacingS = 8.0;
  static const double spacingM = 12.0;
  static const double spacingL = 16.0;
  static const double spacingXL = 24.0;
  static const double spacingXXL = 32.0;

  // Radius
  static const double radiusSmall = 6.0;
  static const double radiusMedium = 8.0;
  static const double radiusLarge = 12.0;
  static const double radiusCircular = 100.0;

  // Widget specific
  static BoxDecoration get cardDecoration => BoxDecoration(
        color: backgroundSecondary,
        borderRadius: BorderRadius.circular(radiusLarge),
        boxShadow: [BoxShadow(color: Colors.black.withValues(alpha: 0.1), blurRadius: 4, offset: const Offset(0, 2))],
      );

  static InputDecoration get inputDecoration => InputDecoration(
        filled: true,
        fillColor: backgroundTertiary,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(radiusMedium), borderSide: BorderSide.none),
      );

  static BoxDecoration get chipDecoration => BoxDecoration(
        color: backgroundTertiary.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(radiusCircular),
      );
}

/// Theme extension to provide app styles as part of the theme
class AppTheme extends ThemeExtension<AppTheme> {
  final TextStyle title;
  final TextStyle subtitle;
  final TextStyle body;
  final TextStyle caption;
  final TextStyle small;
  final TextStyle label;

  AppTheme({
    required this.title,
    required this.subtitle,
    required this.body,
    required this.caption,
    required this.small,
    required this.label,
  });

  @override
  ThemeExtension<AppTheme> copyWith({
    TextStyle? title,
    TextStyle? subtitle,
    TextStyle? body,
    TextStyle? caption,
    TextStyle? small,
    TextStyle? label,
  }) {
    return AppTheme(
      title: title ?? this.title,
      subtitle: subtitle ?? this.subtitle,
      body: body ?? this.body,
      caption: caption ?? this.caption,
      small: small ?? this.small,
      label: label ?? this.label,
    );
  }

  @override
  ThemeExtension<AppTheme> lerp(ThemeExtension<AppTheme>? other, double t) {
    if (other is! AppTheme) {
      return this;
    }
    return AppTheme(
      title: TextStyle.lerp(title, other.title, t)!,
      subtitle: TextStyle.lerp(subtitle, other.subtitle, t)!,
      body: TextStyle.lerp(body, other.body, t)!,
      caption: TextStyle.lerp(caption, other.caption, t)!,
      small: TextStyle.lerp(small, other.small, t)!,
      label: TextStyle.lerp(label, other.label, t)!,
    );
  }

  /// Apply AppTheme to ThemeData
  static ThemeData applyToTheme(ThemeData theme) {
    return theme.copyWith(
      extensions: [
        AppTheme(
          title: AppStyles.title,
          subtitle: AppStyles.subtitle,
          body: AppStyles.body,
          caption: AppStyles.caption,
          small: AppStyles.small,
          label: AppStyles.label,
        ),
      ],
    );
  }
}
