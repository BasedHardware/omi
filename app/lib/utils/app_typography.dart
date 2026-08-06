import 'package:flutter/material.dart';

/// The app's typographic system.
///
/// Omi ships a single UI typeface — Space Grotesk — a geometric grotesque with
/// enough character to read as modern and technical, but with conventional
/// letterforms so transcripts, chat, and dense lists stay legible at 12–15px.
///
/// It is applied globally through [ThemeData.fontFamily] in `main.dart`, so the
/// several hundred inline `TextStyle(...)`s scattered across the app inherit it
/// without needing to name a family. Only the *tracking* and *line height* below
/// have to be applied deliberately, via [AppType].
class AppFonts {
  AppFonts._();

  /// Family name declared in `pubspec.yaml`. Weights 300–700 are bundled;
  /// heavier requests (w800/w900) fall back to the 700 cut.
  static const String ui = 'Space Grotesk';
}

/// Tracking (letter spacing) that keeps Space Grotesk from feeling loose.
///
/// The face is wide by default. Large text needs negative tracking to read as
/// deliberate rather than stretched; small text needs a touch of positive
/// tracking to stay open at low pixel sizes. These are the two numbers that do
/// most of the visual work.
class AppTracking {
  AppTracking._();

  /// Display and hero numerals (28px+).
  static const double display = -1.0;

  /// Headlines and page titles (20–27px).
  static const double headline = -0.6;

  /// Section headers and card titles (16–19px).
  static const double title = -0.3;

  /// Body copy (14–15px) — the face is comfortable here untouched.
  static const double body = 0.0;

  /// Captions, labels, tab bar items (≤13px).
  static const double label = 0.1;
}

/// The type ramp. Prefer these over ad-hoc [TextStyle]s in new UI.
///
/// Colors are intentionally omitted from most entries so call sites can set
/// their own emphasis; where a default is given it is the primary-on-dark white.
class AppType {
  AppType._();

  static const TextStyle displayLarge = TextStyle(
    fontSize: 34,
    fontWeight: FontWeight.w700,
    letterSpacing: AppTracking.display,
    height: 1.1,
    color: Colors.white,
  );

  static const TextStyle displayMedium = TextStyle(
    fontSize: 28,
    fontWeight: FontWeight.w700,
    letterSpacing: AppTracking.display,
    height: 1.15,
    color: Colors.white,
  );

  static const TextStyle headlineLarge = TextStyle(
    fontSize: 24,
    fontWeight: FontWeight.w600,
    letterSpacing: AppTracking.headline,
    height: 1.2,
    color: Colors.white,
  );

  static const TextStyle headlineMedium = TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w600,
    letterSpacing: AppTracking.headline,
    height: 1.25,
    color: Colors.white,
  );

  /// Section headers — "Today", "Mind Map", "Daily Recaps".
  static const TextStyle titleLarge = TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w600,
    letterSpacing: AppTracking.title,
    height: 1.3,
    color: Colors.white,
  );

  static const TextStyle titleMedium = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w600,
    letterSpacing: AppTracking.title,
    height: 1.35,
    color: Colors.white,
  );

  static const TextStyle bodyLarge = TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w400,
    letterSpacing: AppTracking.body,
    height: 1.45,
    color: Colors.white,
  );

  /// Default body — conversation summaries, task titles, chat.
  static const TextStyle bodyMedium = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w400,
    letterSpacing: AppTracking.body,
    height: 1.45,
    color: Colors.white,
  );

  static const TextStyle bodySmall = TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w400,
    letterSpacing: AppTracking.label,
    height: 1.4,
  );

  static const TextStyle labelMedium = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w500,
    letterSpacing: AppTracking.label,
    height: 1.3,
  );

  static const TextStyle labelSmall = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    letterSpacing: AppTracking.label,
    height: 1.3,
  );

  /// The [TextTheme] handed to [ThemeData].
  ///
  /// Widgets that pull from `Theme.of(context).textTheme` get the full ramp,
  /// including tracking and line height. Widgets using bare inline styles still
  /// pick up the family from [ThemeData.fontFamily] — they just miss the
  /// tracking, which is why headings worth the polish should migrate here.
  static TextTheme textTheme() {
    return TextTheme(
      displayLarge: displayLarge,
      displayMedium: displayMedium,
      headlineLarge: headlineLarge,
      headlineMedium: headlineMedium,
      titleLarge: titleLarge,
      titleMedium: titleMedium,
      bodyLarge: bodyLarge,
      bodyMedium: bodyMedium,
      bodySmall: bodySmall.copyWith(color: Colors.grey.shade300),
      labelMedium: labelMedium.copyWith(color: Colors.grey.shade200),
      labelSmall: labelSmall.copyWith(color: Colors.grey.shade400),
    );
  }
}
