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
/// Built from the active [OmiPalette] (`OmiColors.palette`), so it is a real dark or light scheme:
/// [ColorScheme.primary] is the neutral accent (white on dark, ink on light) and
/// [ColorScheme.surface] is the page. The app builds it again after every palette switch. Page
/// backgrounds name [OmiColors.surface0] directly; never read `colorScheme.primary` as a background.
ThemeData buildOmiTheme() {
  final light = OmiColors.isLight;
  final scheme = light
      ? ColorScheme.light(
          primary: OmiColors.accent,
          onPrimary: OmiColors.onAccent,
          secondary: OmiColors.surface3,
          onSecondary: OmiColors.textPrimary,
          surface: OmiColors.surface0,
          onSurface: OmiColors.textPrimary,
          error: OmiColors.danger,
        )
      : ColorScheme.dark(
          primary: OmiColors.accent,
          onPrimary: OmiColors.onAccent,
          // Unchanged from the previous theme: chips, checkboxes and a few dialogs still read it.
          secondary: const Color(0xFF35343B),
          surface: OmiColors.surface0,
          onSurface: OmiColors.textPrimary,
          error: OmiColors.danger,
        );

  return ThemeData(
    useMaterial3: false,
    brightness: light ? Brightness.light : Brightness.dark,
    colorScheme: scheme,
    canvasColor: OmiColors.surface0,
    cardColor: OmiColors.surface1,
    dividerColor: OmiColors.border,
    iconTheme: IconThemeData(color: OmiColors.textPrimary),
    scaffoldBackgroundColor: OmiColors.surface0,
    appBarTheme: AppBarThemeData(
      backgroundColor: OmiColors.surface0,
      foregroundColor: OmiColors.textPrimary,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: true,
      titleTextStyle: OmiType.headline,
      iconTheme: IconThemeData(color: OmiColors.textPrimary),
      actionsIconTheme: IconThemeData(color: OmiColors.textPrimary),
      systemOverlayStyle: light ? SystemUiOverlayStyle.dark : SystemUiOverlayStyle.light,
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
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
    dialogTheme: DialogThemeData(
      backgroundColor: OmiColors.surface1,
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.lgAll),
    ),
    // No `showDragHandle` here: many sheets still draw their own handle. `showOmiSheet` turns the
    // framework handle on; the size and colour below make it look the same everywhere.
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: OmiColors.sheet,
      modalBackgroundColor: OmiColors.sheet,
      dragHandleColor: OmiColors.border,
      dragHandleSize: const Size(36, 4),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.disabled)) return OmiColors.textDisabled;
        if (states.contains(WidgetState.selected)) return OmiColors.accent;
        return OmiColors.textSecondary;
      }),
      trackColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.disabled)) return OmiColors.surface2;
        if (states.contains(WidgetState.selected)) return OmiColors.selection;
        return OmiColors.surface3;
      }),
    ),
    // v2: the remaining Material controls take the neutral palette instead of Material 2
    // defaults (which read the legacy violet-grey `secondary` or grey[800]).
    checkboxTheme: CheckboxThemeData(
      fillColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.disabled)) return OmiColors.surface3;
        if (states.contains(WidgetState.selected)) return OmiColors.accent;
        return Colors.transparent;
      }),
      checkColor: WidgetStatePropertyAll(OmiColors.onAccent),
      side: BorderSide(color: OmiColors.textTertiary, width: 1.5),
    ),
    sliderTheme: SliderThemeData(
      activeTrackColor: OmiColors.accent,
      inactiveTrackColor: OmiColors.surface3,
      thumbColor: OmiColors.accent,
      overlayColor: OmiColors.textPrimary.withValues(alpha: 0.12),
    ),
    floatingActionButtonTheme: FloatingActionButtonThemeData(
      backgroundColor: OmiColors.accent,
      foregroundColor: OmiColors.onAccent,
      elevation: 0,
      shape: const StadiumBorder(),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: OmiColors.surface2,
      selectedColor: OmiColors.accent,
      checkmarkColor: OmiColors.onAccent,
      labelStyle: OmiType.footnote.copyWith(fontWeight: FontWeight.w600),
      secondaryLabelStyle: OmiType.footnote.copyWith(color: OmiColors.onAccent, fontWeight: FontWeight.w600),
      side: BorderSide.none,
      shape: const StadiumBorder(),
    ),
    tabBarTheme: TabBarThemeData(
      labelColor: OmiColors.textPrimary,
      unselectedLabelColor: OmiColors.textSecondary,
      indicatorColor: OmiColors.accent,
      dividerColor: OmiColors.border,
    ),
    dividerTheme: DividerThemeData(color: OmiColors.border, thickness: 0.5, space: 1),
    popupMenuTheme: PopupMenuThemeData(
      color: OmiColors.surface2,
      textStyle: OmiType.subhead,
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.mdAll),
    ),
    textTheme: TextTheme(
      titleLarge: TextStyle(fontSize: 18, color: OmiColors.textPrimary),
      titleMedium: TextStyle(fontSize: 16, color: OmiColors.textPrimary),
      bodyMedium: TextStyle(fontSize: 14, color: OmiColors.textPrimary),
      labelMedium: TextStyle(fontSize: 12, color: OmiColors.textPrimary),
    ),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: OmiColors.accent,
      selectionColor: OmiColors.textPrimary.withValues(alpha: light ? 0.18 : 0.24),
      selectionHandleColor: OmiColors.accent,
    ),
    cupertinoOverrideTheme: CupertinoThemeData(
      brightness: light ? Brightness.light : Brightness.dark,
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
