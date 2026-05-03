import 'package:flutter/material.dart';

import '../xml_parser.dart';

/// Base class for all generative UI tag parsers.
/// Extend this class to add support for new XML tag types.
abstract class BaseTagParser {
  /// The regex pattern to match this tag type in content.
  RegExp get pattern;

  /// Parse the matched content and return a ContentSegment.
  /// Returns null if parsing fails.
  ContentSegment? parse(RegExpMatch match);

  /// Check if content contains this tag type.
  bool containsTag(String content) => pattern.hasMatch(content);

  /// Find all matches of this tag in content.
  Iterable<RegExpMatch> findMatches(String content) => pattern.allMatches(content);

  /// Helper to parse key="value" attributes from a string.
  @protected
  Map<String, String> parseAttributes(String attributeString) {
    final attributes = <String, String>{};
    final attributePattern = RegExp(r'(\w+)\s*=\s*"([^"]*)"');

    for (final match in attributePattern.allMatches(attributeString)) {
      final key = match.group(1);
      final value = match.group(2);
      if (key != null && value != null) {
        attributes[key] = value;
      }
    }

    return attributes;
  }

  /// Named color map for common colors.
  static const _namedColors = <String, Color>{
    'yellow': Color(0xFFF9D71C),
    'orange': Color(0xFFF97316),
    'green': Color(0xFF22C55E),
    'blue': Color(0xFF3B82F6),
    'purple': Color(0xFF8B5CF6),
    'red': Color(0xFFEF4444),
    'pink': Color(0xFFEC4899),
    'cyan': Color(0xFF06B6D4),
    'amber': Color(0xFFF59E0B),
    'lime': Color(0xFF84CC16),
    'teal': Color(0xFF14B8A6),
    'indigo': Color(0xFF6366F1),
    'white': Color(0xFFFFFFFF),
    'black': Color(0xFF000000),
    'gray': Color(0xFF6B7280),
    'grey': Color(0xFF6B7280),
  };

  /// Helper to parse a color from hex string (e.g. "#8B5CF6") or named color.
  @protected
  Color? parseColor(String? colorString) {
    if (colorString == null || colorString.isEmpty) return null;

    final normalized = colorString.trim().toLowerCase();

    if (_namedColors.containsKey(normalized)) {
      return _namedColors[normalized];
    }

    if (normalized.startsWith('#') || normalized.length == 6 || normalized.length == 8) {
      try {
        String hex = normalized.replaceFirst('#', '');
        if (hex.length == 6) {
          hex = 'FF$hex';
        }
        return Color(int.parse(hex, radix: 16));
      } catch (e) {
        // Fall through.
      }
    }

    return null;
  }
}
