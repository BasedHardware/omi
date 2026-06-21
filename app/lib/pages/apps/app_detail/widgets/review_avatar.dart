import 'package:flutter/material.dart';

/// Initials avatar rendered entirely locally — no network dependency.
///
/// Review reviewer photos are not stored anywhere, so avatars were previously
/// generated from a third-party service. When that service is unreachable the
/// image request hangs (never errors), leaving a blank placeholder circle. This
/// draws a deterministic colored circle with the reviewer's initial instead.
class ReviewAvatar extends StatelessWidget {
  final String seed;
  final String username;
  final double size;
  final Color? backgroundColor;
  final Color? foregroundColor;

  const ReviewAvatar({
    super.key,
    required this.seed,
    required this.username,
    this.size = 40,
    this.backgroundColor,
    this.foregroundColor,
  });

  static const List<Color> _palette = [
    Color(0xFF6C5CE7),
    Color(0xFF00B894),
    Color(0xFF0984E3),
    Color(0xFFE17055),
    Color(0xFFD63031),
    Color(0xFF00CEC9),
    Color(0xFFE84393),
    Color(0xFFFDCB6E),
  ];

  String get _initial => username.isNotEmpty ? username[0].toUpperCase() : 'A';

  // Deterministic FNV-1a hash. Dart's String.hashCode is seeded per run
  // (hash-flood mitigation), so the same reviewer could otherwise get a
  // different color on every app launch.
  static int _stableHash(String s) {
    var hash = 0x811c9dc5;
    for (final unit in s.codeUnits) {
      hash ^= unit;
      hash = (hash * 0x01000193) & 0xffffffff;
    }
    return hash;
  }

  Color get _background {
    if (backgroundColor != null) return backgroundColor!;
    final key = seed.isNotEmpty ? seed : username;
    return _palette[_stableHash(key) % _palette.length];
  }

  // White initials wash out on the light palette entries; pick a legible
  // foreground from the background's luminance when no override is given.
  Color get _foreground {
    if (foregroundColor != null) return foregroundColor!;
    return _background.computeLuminance() > 0.5 ? const Color(0xFF1F1F25) : Colors.white;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: _background, shape: BoxShape.circle),
      child: Text(
        _initial,
        style: TextStyle(color: _foreground, fontSize: size * 0.45, fontWeight: FontWeight.w600),
      ),
    );
  }
}
