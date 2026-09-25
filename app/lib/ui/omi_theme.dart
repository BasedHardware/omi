import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:intl/intl.dart';

import 'package:omi/ui/omi_tokens.dart';

/// The app's one [ThemeData]. `main.dart` and the screenshot harness
/// (`integration_test/visual_audit/`) both build their theme here, so the two cannot drift.
///
/// Material 2 stays on (`useMaterial3: false`); a Material 3 flip is a separate change.
///
/// The colour scheme is a real dark scheme: [ColorScheme.primary] is the neutral accent (white)
/// and [ColorScheme.surface] is the black page. Page backgrounds name [OmiColors.surface0]
/// directly; never read `colorScheme.primary` as a background.
ThemeData buildOmiTheme() {
  const scheme = ColorScheme.dark(
    primary: OmiColors.accent,
    onPrimary: OmiColors.onAccent,
    // Unchanged from the previous theme: chips, checkboxes and a few dialogs still read it.
    secondary: Color(0xFF35343B),
    surface: OmiColors.surface0,
    onSurface: OmiColors.textPrimary,
    error: OmiColors.danger,
  );

  return ThemeData(
    useMaterial3: false,
    colorScheme: scheme,
    scaffoldBackgroundColor: OmiColors.surface0,
    appBarTheme: const AppBarThemeData(
      backgroundColor: OmiColors.surface0,
      foregroundColor: OmiColors.textPrimary,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: true,
      titleTextStyle: OmiType.headline,
      iconTheme: IconThemeData(color: OmiColors.textPrimary),
      actionsIconTheme: IconThemeData(color: OmiColors.textPrimary),
      systemOverlayStyle: SystemUiOverlayStyle.light,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: OmiColors.accent,
      refreshBackgroundColor: OmiColors.surface2,
      linearTrackColor: OmiColors.surface3,
      circularTrackColor: Colors.transparent,
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: OmiColors.surface2,
      contentTextStyle: OmiType.callout.copyWith(fontWeight: FontWeight.w500),
      actionTextColor: OmiColors.textPrimary,
      closeIconColor: OmiColors.textSecondary,
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.mdAll),
      elevation: 0,
    ),
    dialogTheme: const DialogThemeData(
      backgroundColor: OmiColors.surface1,
      shape: RoundedRectangleBorder(borderRadius: OmiRadius.lgAll),
    ),
    // No `showDragHandle` here: many sheets still draw their own handle. `showOmiSheet` turns the
    // framework handle on; the size and colour below make it look the same everywhere.
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: OmiColors.surface1,
      modalBackgroundColor: OmiColors.surface1,
      dragHandleColor: OmiColors.border,
      dragHandleSize: Size(36, 4),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.disabled)) return OmiColors.textDisabled;
        if (states.contains(WidgetState.selected)) return OmiColors.accent;
        return OmiColors.textSecondary;
      }),
      trackColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.disabled)) return OmiColors.surface2;
        if (states.contains(WidgetState.selected)) return OmiColors.accent.withValues(alpha: 0.5);
        return OmiColors.surface3;
      }),
    ),
    textTheme: TextTheme(
      titleLarge: const TextStyle(fontSize: 18, color: Colors.white),
      titleMedium: const TextStyle(fontSize: 16, color: Colors.white),
      bodyMedium: const TextStyle(fontSize: 14, color: Colors.white),
      labelMedium: TextStyle(fontSize: 12, color: Colors.grey.shade200),
    ),
    textSelectionTheme: const TextSelectionThemeData(
      cursorColor: OmiColors.accent,
      selectionColor: Colors.white24,
      selectionHandleColor: OmiColors.accent,
    ),
    cupertinoOverrideTheme: const CupertinoThemeData(
      primaryColor: OmiColors.accent, // Controls the selection handles on iOS
    ),
  );
}

/// Makes `intl`'s default locale follow the app's resolved locale, so a `DateFormat` or
/// `NumberFormat` built without an explicit locale stops formatting as en_US.
///
/// Call it where the locale is resolved (the `MaterialApp.builder`). It is a safety net:
/// formatters should still pass the locale explicitly. A locale that `intl` has no date symbols
/// for is ignored rather than set, because `DateFormat` would throw on it.
void syncIntlDefaultLocale(Locale locale) {
  final tag = Intl.canonicalizedLocale(locale.toLanguageTag());
  if (Intl.defaultLocale == tag) return;
  if (DateFormat.localeExists(tag)) {
    Intl.defaultLocale = tag;
  } else if (DateFormat.localeExists(locale.languageCode)) {
    Intl.defaultLocale = locale.languageCode;
  }
}
