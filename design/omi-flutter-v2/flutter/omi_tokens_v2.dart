// Omi v2 "Midnight Graphite" values for the EXISTING token names in app/lib/ui/omi_tokens.dart.
//
// How to apply: do not add this file to the app. Copy the values below into
// app/lib/ui/omi_tokens.dart (same class and field names), so every screen that already uses
// OmiColors / OmiType / OmiRadius / OmiSpacing restyles at once. That keeps the mobile UX
// contract (INV-UI-3): no Color(0x…) literals in pages, only tokens.
//
// Fields marked NEW do not exist on main yet. Add them to the same classes.

import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';

abstract final class OmiColorsV2 {
  // Surfaces: midnight ink instead of pure black / iOS system greys.
  static const Color surface0 = Color(0xFF0A0C10); // screen background
  static const Color surface1 = Color(0xFF14171D); // cards, grouped rows
  static const Color surface2 = Color(0xFF1C2029); // controls, fields, chips
  static const Color surface3 = Color(0xFF272C36); // pressed, secondary buttons, tiles
  static const Color border = Color(0x338C96AA); // hairlines (0.5 pt)

  static const Color textPrimary = Color(0xFFECEEF2);
  static const Color textSecondary = Color(0xFF9AA1AD);
  static const Color textTertiary = Color(0xFF7F8693); // >= 4.5:1 on surface0 and surface1
  static const Color textDisabled = Color(0xFF5A606B);

  static const Color accent = Color(0xFFECEEF2); // primary buttons are neutral (INV-UI-1: no purple)
  static const Color onAccent = Color(0xFF0A0C10);

  static const Color success = Color(0xFF30D158);
  static const Color successSurface = Color(0x2630D158);
  static const Color warning = Color(0xFFFFB547);
  static const Color danger = Color(0xFFFF6B61);
  static const Color dangerSurface = Color(0x24FF6B61);

  // NEW
  static const Color sheet = Color(0xFF111419); // modal sheet background
  static const Color selection = Color(0xFF6F86AD); // toggles on, selected segment accents
  static const Color live = Color(0xFF4C9BFF); // ONLY "audio is being captured right now". Never decoration.
}

/// Light theme twin (phase 2 — the app is dark-only today). Same roles, same names.
abstract final class OmiColorsV2Light {
  static const Color surface0 = Color(0xFFF2F3F6);
  static const Color surface1 = Color(0xFFFFFFFF);
  static const Color surface2 = Color(0xFFE8EAEF);
  static const Color surface3 = Color(0xFFDEE1E7);
  static const Color border = Color(0x243C4350);
  static const Color textPrimary = Color(0xFF14171D);
  static const Color textSecondary = Color(0xFF5B6270);
  static const Color textTertiary = Color(0xFF6B7280);
  static const Color textDisabled = Color(0xFFA3A9B3);
  static const Color accent = Color(0xFF14171D);
  static const Color onAccent = Color(0xFFFFFFFF);
  static const Color warning = Color(0xFFA35F00);
  static const Color danger = Color(0xFFD2342A);
  static const Color sheet = Color(0xFFF7F8FA);
  static const Color selection = Color(0xFF3F5B8C);
  static const Color live = Color(0xFF4C9BFF);
}

/// Radii used by the designs. Keep main's sm/md/lg/xl; add the NEW ones.
abstract final class OmiRadiusV2 {
  static const double row = 22; // NEW grouped rows
  static const double card = 26; // NEW cards on Home / lists
  static const double cardLarge = 28; // NEW hero cards
  static const double tabBar = 32; // NEW floating tab bar capsule
  static const double sheet = 40; // NEW large sheet top corners (iOS); Android uses 28
  // Rule: nested radius = outer radius - padding (concentric corners).
}

/// Motion: one spring-like curve for everything that moves; durations stay on OmiMotion.
abstract final class OmiMotionV2 {
  /// The design's cubic-bezier(.32,.72,0,1) — iOS sheet/navigation feel. Use for push, sheets, cards.
  static const Curve spring = Cubic(0.32, 0.72, 0, 1);

  /// Success moments only (check pops, star, plan picked).
  static const Curve bouncy = Cubic(0.34, 1.56, 0.64, 1);

  static const Duration navigation = Duration(milliseconds: 500);
  static const Duration sheet = Duration(milliseconds: 450);
  static const Duration press = Duration(milliseconds: 180); // scale to 0.96, opacity 0.82
  static const Duration ledBreathe = Duration(milliseconds: 2400);
}

/// Sizes the designs rely on.
abstract final class OmiSizeV2 {
  static const double minTap = 44;
  static const double primaryButton = 50; // capsule; grows with text size
  static const double navButton = 44; // glass circle
  static const double tabBar = 64;
  static const double askButton = 64;
  static const double screenMargin = 16;
  static const double rowMinHeight = 52;
}
