import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Omi's colour tokens. The app is dark-only; these are the only colours new UI should name.
///
/// Surfaces step up from the black page: [surface0] page, [surface1] cards, grouped settings and
/// sheets, [surface2] controls and elevated rows sitting on a card, [surface3] pressed or selected
/// fills. They are the iOS dark system greys, which are also the near-blacks this app already
/// used most (`0xFF1C1C1E` for settings cards and sheets, `0xFF2C2C2E`/`0xFF2A2A2E` for chips and
/// elevated rows). `0xFF35343B` and `0xFF1F1F25` were dropped because they carry a blue-violet
/// tint that the neutral palette (INV-UI-1) does not want.
///
/// Accents and primary actions are neutral: [accent] is white with [onAccent] black text.
/// Status colours ([success], [warning], [danger]) are the iOS dark-mode system colours, chosen so
/// that each is legible as text on [surface0] and [surface1] (danger is 6.2:1 on black, 5.0:1 on
/// [surface1]).
///
/// `AppStyles` (utils/ui_guidelines.dart) and the `ResponsiveHelper` palette predate these tokens.
/// Do not add new uses of them; migrate a file to [OmiColors] when you touch it.
abstract final class OmiColors {
  /// Page background.
  static const Color surface0 = Color(0xFF000000);

  /// Cards, grouped settings, sheets, dialogs, search fields.
  static const Color surface1 = Color(0xFF1C1C1E);

  /// Controls and rows that sit on a [surface1] card; secondary buttons; snack bars.
  static const Color surface2 = Color(0xFF2C2C2E);

  /// Pressed and selected fills; the highest step.
  static const Color surface3 = Color(0xFF3A3A3C);

  /// Hairline dividers and card outlines.
  static const Color border = Color(0xFF3C3C43);

  /// Titles and body text.
  static const Color textPrimary = Color(0xFFFFFFFF);

  /// Descriptions and supporting text (7.7:1 on [surface1]).
  static const Color textSecondary = Color(0xFFAEAEB2);

  /// Metadata, placeholders, leading icons (5.2:1 on [surface1], 6.5:1 on black). Never darker:
  /// greys below this fail WCAG AA on the app's cards.
  static const Color textTertiary = Color(0xFF8E8E93);

  /// Labels of disabled controls only. Exempt from contrast rules because it marks "unavailable";
  /// never use it for text a reader needs.
  static const Color textDisabled = Color(0xFF636366);

  /// The accent: primary buttons, selected state, switches, spinners. Neutral per INV-UI-1.
  static const Color accent = Color(0xFFFFFFFF);

  /// Text and icons drawn on [accent].
  static const Color onAccent = Color(0xFF000000);

  /// Success status, as text or icon.
  static const Color success = Color(0xFF30D158);

  /// Tinted background behind [success] content (e.g. a "Connected" banner).
  static const Color successSurface = Color(0x2630D158);

  /// Warning status, as text or icon.
  static const Color warning = Color(0xFFFF9F0A);

  /// Destructive actions and errors, as text or icon.
  static const Color danger = Color(0xFFFF453A);

  /// Tinted background behind [danger] content (destructive buttons, error banners).
  static const Color dangerSurface = Color(0x26FF453A);
}

/// Omi's type ramp, modelled on iOS text styles so that sizes land where the app's text already
/// sat (16 is `callout`, 17 is `body`, 20 is `title3`).
///
/// Every style carries [OmiColors.textPrimary]; override with `copyWith(color: ...)`.
abstract final class OmiType {
  /// 11 — badges, timestamps in dense rows.
  static const TextStyle caption = TextStyle(fontSize: 11, fontWeight: FontWeight.w400, color: OmiColors.textPrimary);

  /// 13 — secondary lines under a row title, footers, hints.
  static const TextStyle footnote = TextStyle(fontSize: 13, fontWeight: FontWeight.w400, color: OmiColors.textPrimary);

  /// 15 — descriptions, compact button labels, search text.
  static const TextStyle subhead = TextStyle(fontSize: 15, fontWeight: FontWeight.w400, color: OmiColors.textPrimary);

  /// 16 — button labels, snack bars, dense body copy.
  static const TextStyle callout = TextStyle(fontSize: 16, fontWeight: FontWeight.w400, color: OmiColors.textPrimary);

  /// 17 — row titles and reading text.
  static const TextStyle body = TextStyle(fontSize: 17, fontWeight: FontWeight.w400, color: OmiColors.textPrimary);

  /// 17 semibold — app bar titles, sheet titles, emphasised row titles.
  static const TextStyle headline = TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: OmiColors.textPrimary);

  /// 20 semibold — section headers.
  static const TextStyle title3 = TextStyle(fontSize: 20, fontWeight: FontWeight.w600, color: OmiColors.textPrimary);

  /// 24 semibold — in-body page headings (tab roots).
  static const TextStyle title2 = TextStyle(fontSize: 24, fontWeight: FontWeight.w600, color: OmiColors.textPrimary);

  /// 28 bold — hero headings (onboarding, empty hero).
  static const TextStyle title1 = TextStyle(fontSize: 28, fontWeight: FontWeight.w700, color: OmiColors.textPrimary);

  /// 34 bold — the largest display text; one per screen at most.
  static const TextStyle largeTitle =
      TextStyle(fontSize: 34, fontWeight: FontWeight.w700, color: OmiColors.textPrimary);
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
