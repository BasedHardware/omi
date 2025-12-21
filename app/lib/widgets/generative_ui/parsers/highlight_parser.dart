import 'package:flutter/material.dart';
import '../models/highlight_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for <highlight> tags
/// Supports: <highlight>text</highlight> or <highlight color="#F97316">text</highlight>
/// Also supports named colors: yellow, orange, green, blue, purple, red, pink
class HighlightParser extends BaseTagParser {
  /// Named color map for common highlight colors
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
  };

  @override
  RegExp get pattern => RegExp(
        r'<highlight(?:\s+color="([^"]*)")?>([\s\S]*?)</highlight>',
        caseSensitive: false,
        multiLine: true,
      );

  @override
  bool containsTag(String content) => pattern.hasMatch(content);

  @override
  Iterable<RegExpMatch> findMatches(String content) => pattern.allMatches(content);

  @override
  ContentSegment? parse(RegExpMatch match) {
    final colorAttr = match.group(1)?.trim().toLowerCase() ?? '';
    final text = match.group(2)?.trim() ?? '';

    if (text.isEmpty) return null;

    // Parse color from attribute or use default yellow
    Color highlightColor = const Color(0xFFF9D71C); // Default yellow

    if (colorAttr.isNotEmpty) {
      // Check for named color first
      if (_namedColors.containsKey(colorAttr)) {
        highlightColor = _namedColors[colorAttr]!;
      } else if (colorAttr.startsWith('#')) {
        // Try to parse hex color
        try {
          final hexColor = colorAttr.replaceFirst('#', '');
          highlightColor = Color(int.parse('FF$hexColor', radix: 16));
        } catch (_) {
          // Keep default yellow on parse error
        }
      }
    }

    return HighlightSegment(HighlightData(text: text, color: highlightColor));
  }
}
