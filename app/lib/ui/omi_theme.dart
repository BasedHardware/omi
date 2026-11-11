import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import 'package:omi/ui/omi_tokens.dart';

/// Builds the light and dark Material 2 themes from the same semantic palette.
ThemeData buildOmiTheme({Brightness brightness = Brightness.dark}) {
  final palette = OmiColors.forBrightness(brightness);
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme(
    brightness: brightness,
    primary: palette.accent,
    onPrimary: palette.onAccent,
    secondary: dark ? const Color(0xFF35343B) : palette.surface3,
    onSecondary: palette.textPrimary,
    error: palette.danger,
    onError: palette.onAccent,
    surface: palette.surface0,
    onSurface: palette.textPrimary,
  );
  final overlay = dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark;

  return ThemeData(
    useMaterial3: false,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: palette.surface0,
    appBarTheme: AppBarThemeData(
      backgroundColor: palette.surface0,
      foregroundColor: palette.textPrimary,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: true,
      titleTextStyle: TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: palette.textPrimary),
      iconTheme: IconThemeData(color: palette.textPrimary),
      actionsIconTheme: IconThemeData(color: palette.textPrimary),
      systemOverlayStyle: overlay,
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      color: palette.accent,
      refreshBackgroundColor: palette.surface2,
      linearTrackColor: palette.surface3,
      circularTrackColor: Colors.transparent,
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: palette.surface2,
      contentTextStyle: TextStyle(fontSize: 16, fontWeight: FontWeight.w500, color: palette.textPrimary),
      actionTextColor: palette.accent,
      closeIconColor: palette.textSecondary,
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.mdAll),
      elevation: 0,
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: palette.surface1,
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.lgAll),
      elevation: dark ? null : 0,
      shadowColor: dark ? null : Colors.transparent,
      surfaceTintColor: dark ? null : Colors.transparent,
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: palette.surface1,
      modalBackgroundColor: palette.surface1,
      dragHandleColor: palette.border,
      dragHandleSize: const Size(36, 4),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.disabled)) return palette.textDisabled;
        if (states.contains(WidgetState.selected)) return palette.accent;
        return palette.textSecondary;
      }),
      trackColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.disabled)) return palette.surface2;
        if (states.contains(WidgetState.selected)) return palette.accent.withValues(alpha: 0.5);
        return palette.surface3;
      }),
    ),
    textTheme: TextTheme(
      titleLarge: TextStyle(fontSize: 18, color: palette.textPrimary),
      titleMedium: TextStyle(fontSize: 16, color: palette.textPrimary),
      bodyMedium: TextStyle(fontSize: 14, color: palette.textPrimary),
      labelMedium: TextStyle(fontSize: 12, color: palette.textSecondary),
    ),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: palette.accent,
      selectionColor: palette.accent.withValues(alpha: 0.24),
      selectionHandleColor: palette.accent,
    ),
    cupertinoOverrideTheme: CupertinoThemeData(
      brightness: brightness,
      primaryColor: palette.accent,
    ),
  );
}

/// Keeps implicit intl formatters aligned with the resolved app locale.
void syncIntlDefaultLocale(Locale locale) {
  final tag = Intl.canonicalizedLocale(locale.toLanguageTag());
  if (Intl.defaultLocale == tag) return;
  if (DateFormat.localeExists(tag)) {
    Intl.defaultLocale = tag;
  } else if (DateFormat.localeExists(locale.languageCode)) {
    Intl.defaultLocale = locale.languageCode;
  }
}
