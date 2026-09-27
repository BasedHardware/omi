import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Omi colour tokens resolve to the selected light or dark appearance.
///
/// Surfaces step up from the page: surface0 is the page, surface1 holds cards and sheets,
/// surface2 holds controls on cards, and surface3 is the selected or pressed fill. The dark
/// palette retains the original iOS dark greys exactly. The light palette uses the iOS grouped
/// background (#F2F2F7), white cards, and neutral light greys.
///
/// Accents and primary actions are neutral: white on black in dark mode, black on white in light mode.
/// Status colours use the corresponding iOS light and dark system variants.
///
/// `AppStyles` and `ResponsiveHelper` predate these tokens. Do not add new uses of them.
///
/// Resolved values for one appearance. The dark values are the original Omi tokens.
@immutable
class OmiPalette {
  const OmiPalette(
      {required this.surface0,
      required this.surface1,
      required this.surface2,
      required this.surface3,
      required this.border,
      required this.textPrimary,
      required this.textSecondary,
      required this.textTertiary,
      required this.textDisabled,
      required this.accent,
      required this.onAccent,
      required this.success,
      required this.successSurface,
      required this.warning,
      required this.danger,
      required this.dangerSurface});

  final Color surface0;
  final Color surface1;
  final Color surface2;
  final Color surface3;
  final Color border;
  final Color textPrimary;
  final Color textSecondary;
  final Color textTertiary;
  final Color textDisabled;
  final Color accent;
  final Color onAccent;
  final Color success;
  final Color successSurface;
  final Color warning;
  final Color danger;
  final Color dangerSurface;

  static const dark = OmiPalette(
    surface0: Color(0xFF000000),
    surface1: Color(0xFF1C1C1E),
    surface2: Color(0xFF2C2C2E),
    surface3: Color(0xFF3A3A3C),
    border: Color(0xFF3C3C43),
    textPrimary: Color(0xFFFFFFFF),
    textSecondary: Color(0xFFAEAEB2),
    textTertiary: Color(0xFF8E8E93),
    textDisabled: Color(0xFF636366),
    accent: Color(0xFFFFFFFF),
    onAccent: Color(0xFF000000),
    success: Color(0xFF30D158),
    successSurface: Color(0x2630D158),
    warning: Color(0xFFFF9F0A),
    danger: Color(0xFFFF453A),
    dangerSurface: Color(0x26FF453A),
  );

  static const light = OmiPalette(
    surface0: Color(0xFFF2F2F7),
    surface1: Color(0xFFFFFFFF),
    surface2: Color(0xFFF2F2F7),
    surface3: Color(0xFFE5E5EA),
    border: Color(0xFFC6C6C8),
    textPrimary: Color(0xFF000000),
    textSecondary: Color(0x993C3C43),
    textTertiary: Color(0xFF636366),
    textDisabled: Color(0xFFAEAEB2),
    accent: Color(0xFF000000),
    onAccent: Color(0xFFFFFFFF),
    success: Color(0xFF34C759),
    successSurface: Color(0x2634C759),
    warning: Color(0xFFFF9500),
    danger: Color(0xFFFF3B30),
    dangerSurface: Color(0x26FF3B30),
  );
}

/// Colors for the resolved appearance. Read during build, after the root updates [active].
abstract final class OmiColors {
  static OmiPalette active = OmiPalette.dark;

  static OmiPalette forBrightness(Brightness brightness) =>
      brightness == Brightness.dark ? OmiPalette.dark : OmiPalette.light;

  static Color get surface0 => active.surface0;
  static Color get surface1 => active.surface1;
  static Color get surface2 => active.surface2;
  static Color get surface3 => active.surface3;
  static Color get border => active.border;
  static Color get textPrimary => active.textPrimary;
  static Color get textSecondary => active.textSecondary;
  static Color get textTertiary => active.textTertiary;
  static Color get textDisabled => active.textDisabled;
  static Color get accent => active.accent;
  static Color get onAccent => active.onAccent;
  static Color get success => active.success;
  static Color get successSurface => active.successSurface;
  static Color get warning => active.warning;
  static Color get danger => active.danger;
  static Color get dangerSurface => active.dangerSurface;
}

/// Omi's type ramp, modelled on iOS text styles so that sizes land where the app's text already
/// sat (16 is `callout`, 17 is `body`, 20 is `title3`).
///
/// Every style carries [OmiColors.textPrimary]; override with `copyWith(color: ...)`.
abstract final class OmiType {
  /// 11 — badges, timestamps in dense rows.
  static TextStyle get caption => TextStyle(fontSize: 11, fontWeight: FontWeight.w400, color: OmiColors.textPrimary);

  /// 13 — secondary lines under a row title, footers, hints.
  static TextStyle get footnote => TextStyle(fontSize: 13, fontWeight: FontWeight.w400, color: OmiColors.textPrimary);

  /// 15 — descriptions, compact button labels, search text.
  static TextStyle get subhead => TextStyle(fontSize: 15, fontWeight: FontWeight.w400, color: OmiColors.textPrimary);

  /// 16 — button labels, snack bars, dense body copy.
  static TextStyle get callout => TextStyle(fontSize: 16, fontWeight: FontWeight.w400, color: OmiColors.textPrimary);

  /// 17 — row titles and reading text.
  static TextStyle get body => TextStyle(fontSize: 17, fontWeight: FontWeight.w400, color: OmiColors.textPrimary);

  /// 17 semibold — app bar titles, sheet titles, emphasised row titles.
  static TextStyle get headline => TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: OmiColors.textPrimary);

  /// 20 semibold — section headers.
  static TextStyle get title3 => TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: OmiColors.textPrimary);

  /// 24 semibold — in-body page headings (tab roots).
  static TextStyle get title2 => TextStyle(fontSize: 24, fontWeight: FontWeight.w600, color: OmiColors.textPrimary);

  /// 28 bold — hero headings (onboarding, empty hero).
  static TextStyle get title1 => TextStyle(fontSize: 28, fontWeight: FontWeight.w700, color: OmiColors.textPrimary);

  /// 34 bold — the largest display text; one per screen at most.
  static TextStyle get largeTitle => TextStyle(fontSize: 34, fontWeight: FontWeight.w700, color: OmiColors.textPrimary);
}

/// Corner radii. Pick by the size of the thing being rounded, not by taste.
abstract final class OmiRadius {
  /// 8 — chips, tags, small inline fills.
  static const double sm = 8;

  /// 12 — buttons, text fields, list cards, snack bars.
  static const double md = 12;

  /// 16 — grouped settings cards, dialogs, large cards.
  static const double lg = 16;

  /// 24 — bottom sheet top corners, search fields.
  static const double xl = 24;

  /// Fully rounded ends (capsules, avatars).
  static const double pill = 999;

  static const BorderRadius smAll = BorderRadius.all(Radius.circular(sm));
  static const BorderRadius mdAll = BorderRadius.all(Radius.circular(md));
  static const BorderRadius lgAll = BorderRadius.all(Radius.circular(lg));
  static const BorderRadius xlAll = BorderRadius.all(Radius.circular(xl));
  static const BorderRadius pillAll = BorderRadius.all(Radius.circular(pill));

  /// Top corners of a bottom sheet.
  static const BorderRadius sheetTop = BorderRadius.vertical(top: Radius.circular(xl));
}

/// Spacing steps. Page gutters are [md] (16) or [lg] (20); stack gaps come from this list.
abstract final class OmiSpacing {
  static const double xxs = 4;
  static const double xs = 8;
  static const double sm = 12;
  static const double md = 16;
  static const double lg = 20;
  static const double xl = 24;
  static const double xxl = 32;
}

/// Animation durations and curves that honour the system's Reduce Motion setting.
///
/// Read durations through [OmiMotion.of] so that `MediaQuery.disableAnimations` (iOS Reduce
/// Motion, Android "Remove animations") turns them into [Duration.zero]:
///
/// ```dart
/// AnimatedOpacity(duration: OmiMotion.of(context).standard, curve: OmiMotion.standardCurve, ...)
/// ```
class OmiMotion {
  const OmiMotion._({required this.quick, required this.standard, required this.emphasized});

  /// Small state changes: a checkmark, a fade of a label, a pressed state.
  final Duration quick;

  /// Most transitions: expanding a row, swapping content, showing a banner.
  final Duration standard;

  /// Large movements that need to be followed by the eye: a panel sliding in.
  final Duration emphasized;

  static const Duration quickDuration = Duration(milliseconds: 150);
  static const Duration standardDuration = Duration(milliseconds: 250);
  static const Duration emphasizedDuration = Duration(milliseconds: 400);

  static const Curve standardCurve = Curves.easeInOut;
  static const Curve emphasizedCurve = Curves.easeOutCubic;

  static const OmiMotion _full =
      OmiMotion._(quick: quickDuration, standard: standardDuration, emphasized: emphasizedDuration);
  static const OmiMotion _reduced =
      OmiMotion._(quick: Duration.zero, standard: Duration.zero, emphasized: Duration.zero);

  /// The durations for this context: all [Duration.zero] when the user asked the system to remove
  /// animations.
  static OmiMotion of(BuildContext context) {
    final reduce = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    return reduce ? _reduced : _full;
  }
}

/// The haptic vocabulary. Use these instead of calling [HapticFeedback] directly so each kind of
/// moment always feels the same.
abstract final class OmiHaptics {
  /// Moving between places: a tab, a segment, a picker value.
  static Future<void> selection() => HapticFeedback.selectionClick();

  /// Flipping a custom toggle or checking an item. (Platform switches give their own feedback.)
  static Future<void> light() => HapticFeedback.lightImpact();

  /// Starting or stopping a recording, finishing a long action.
  static Future<void> medium() => HapticFeedback.mediumImpact();

  /// An action completed and the user should notice (saved, sent, connected).
  static Future<void> success() => HapticFeedback.mediumImpact();

  /// An action failed or was refused.
  static Future<void> error() => HapticFeedback.heavyImpact();
}
