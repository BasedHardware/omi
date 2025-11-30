import 'package:flutter/material.dart';
import '../xml_parser.dart';

/// Base class for all generative UI tag parsers.
/// Extend this class to add support for new XML tag types.
abstract class BaseTagParser {
  /// The regex pattern to match this tag type in content
  RegExp get pattern;

  /// Parse the matched content and return a ContentSegment
  /// Returns null if parsing fails
  ContentSegment? parse(RegExpMatch match);

  /// Check if content contains this tag type
  bool containsTag(String content) => pattern.hasMatch(content);

  /// Find all matches of this tag in content
  Iterable<RegExpMatch> findMatches(String content) => pattern.allMatches(content);

  /// Helper to parse key="value" attributes from a string
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

  /// Helper to parse a color from hex string (e.g., "#8B5CF6")
  @protected
  Color? parseColor(String? colorString) {
    if (colorString == null || colorString.isEmpty) return null;

    try {
      String hex = colorString.replaceFirst('#', '');
      if (hex.length == 6) {
        hex = 'FF$hex'; // Add alpha if not present
      }
      return Color(int.parse(hex, radix: 16));
    } catch (e) {
      debugPrint('Failed to parse color: $colorString');
      return null;
    }
  }
}
