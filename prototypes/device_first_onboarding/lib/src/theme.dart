import 'package:flutter/material.dart';

/// The two visual directions from the Figma exploration
/// ("Omi — Paywall Redesign", pages E and F).
enum DfDirection {
  graphite('Graphite'),
  aurora('Aurora');

  const DfDirection(this.label);

  final String label;
}

/// Colour, radius and type tokens for one direction.
///
/// Everything visual in the prototype reads from here, so moving a direction
/// into the app later means mapping these tokens onto `OmiColors` / `OmiType`.
@immutable
class DfTheme {
  const DfTheme({
    required this.direction,
    required this.background,
    required this.surface,
    required this.surface2,
    required this.border,
    required this.text,
    required this.textSecondary,
    required this.textTertiary,
    required this.accent,
    required this.onAccent,
    required this.success,
    required this.danger,
    required this.buttonRadius,
    required this.headlineTracking,
    this.glow,
  });

  final DfDirection direction;
  final Color background;
  final Color surface;
  final Color surface2;
  final Color border;
  final Color text;
  final Color textSecondary;
  final Color textTertiary;
  final Color accent;
  final Color onAccent;
  final Color success;
  final Color danger;

  /// 14 for Graphite (rounded rectangle), 999 for Aurora (full pill).
  final double buttonRadius;

  /// Letter spacing for headlines, as a fraction of the font size.
  final double headlineTracking;

  /// Aurora only: the "Omi is listening" glow. Reserved for the pendant ring,
  /// progress and badges; never used as a background or for body text.
  final List<Color>? glow;

  /// Pure black, white and nothing else, like an Apple keynote slide.
  static const DfTheme graphite = DfTheme(
    direction: DfDirection.graphite,
    background: Color(0xFF000000),
    surface: Color(0xFF1C1C1E),
    surface2: Color(0xFF2C2C2E),
    border: Color(0xFF38383A),
    text: Color(0xFFFFFFFF),
    textSecondary: Color(0xFFAEAEB2),
    textTertiary: Color(0xFF8E8E93),
    accent: Color(0xFFFFFFFF),
    onAccent: Color(0xFF000000),
    success: Color(0xFF30D158),
    danger: Color(0xFFFF453A),
    buttonRadius: 14,
    headlineTracking: -0.02,
  );

  /// A black canvas and one living light: violet to pink to amber.
  static const DfTheme aurora = DfTheme(
    direction: DfDirection.aurora,
    background: Color(0xFF050507),
    surface: Color(0xFF141418),
    surface2: Color(0xFF1F1F25),
    border: Color(0xFF2A2A33),
    text: Color(0xFFFFFFFF),
    textSecondary: Color(0xFFA1A1AA),
    textTertiary: Color(0xFF71717A),
    accent: Color(0xFFFFFFFF),
    onAccent: Color(0xFF050507),
    success: Color(0xFF34D399),
    danger: Color(0xFFF87171),
    buttonRadius: 999,
    headlineTracking: -0.03,
    glow: <Color>[Color(0xFF7B61FF), Color(0xFFFF6FB5), Color(0xFFFFB86B)],
  );

  static DfTheme of(DfDirection direction) => direction == DfDirection.aurora ? aurora : graphite;

  bool get hasGlow => glow != null;

  /// Fill for "active" accents: the glow on Aurora, solid white on Graphite.
  Gradient get accentGradient => LinearGradient(colors: glow ?? <Color>[accent, accent]);

  /// Fill for small badges ("Best value", "Save $50").
  Gradient get badgeGradient => LinearGradient(colors: glow ?? <Color>[success, success]);

  TextStyle headline(double size) => TextStyle(
    fontSize: size,
    height: 1.1,
    fontWeight: FontWeight.w600,
    letterSpacing: headlineTracking * size,
    color: text,
  );

  TextStyle body({double size = 16, Color? color, FontWeight weight = FontWeight.w400, double height = 1.4}) =>
      TextStyle(fontSize: size, height: height, fontWeight: weight, color: color ?? textSecondary);

  TextStyle label({double size = 15, Color? color, FontWeight weight = FontWeight.w500}) =>
      TextStyle(fontSize: size, fontWeight: weight, color: color ?? text);

  TextStyle eyebrow({Color? color}) =>
      TextStyle(fontSize: 12, fontWeight: FontWeight.w600, letterSpacing: 1.6, color: color ?? textTertiary);
}

/// Provides the active [DfTheme] to every prototype widget below it.
class DfThemeScope extends InheritedWidget {
  const DfThemeScope({super.key, required this.theme, required super.child});

  final DfTheme theme;

  static DfTheme of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<DfThemeScope>()?.theme ?? DfTheme.graphite;

  @override
  bool updateShouldNotify(DfThemeScope oldWidget) => oldWidget.theme != theme;
}
