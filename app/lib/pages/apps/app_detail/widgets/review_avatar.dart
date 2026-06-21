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

  Color get _background {
    if (backgroundColor != null) return backgroundColor!;
    final key = seed.isNotEmpty ? seed : username;
    return _palette[key.hashCode.abs() % _palette.length];
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
        style: TextStyle(color: foregroundColor ?? Colors.white, fontSize: size * 0.45, fontWeight: FontWeight.w600),
      ),
    );
  }
}
