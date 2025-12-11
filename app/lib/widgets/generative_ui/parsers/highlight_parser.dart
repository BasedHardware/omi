import 'package:flutter/material.dart';
import '../models/highlight_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for <highlight> tags
/// Supports: <highlight>text</highlight> or <highlight color="#F97316">text</highlight>
class HighlightParser extends BaseTagParser {
  @override
  RegExp get pattern => RegExp(
        r'<highlight(?:\s+color="([^"]*)")?>([^<]*)</highlight>',
        caseSensitive: false,
        multiLine: true,
      );

  @override
  bool containsTag(String content) => pattern.hasMatch(content);

  @override
  Iterable<RegExpMatch> findMatches(String content) => pattern.allMatches(content);

  @override
  ContentSegment? parse(RegExpMatch match) {
    final colorAttr = match.group(1) ?? '';
    final text = match.group(2)?.trim() ?? '';

    if (text.isEmpty) return null;

    // Parse color from attribute or use default yellow
    Color highlightColor;
    if (colorAttr.isNotEmpty && colorAttr.startsWith('#')) {
      try {
        final hexColor = colorAttr.replaceFirst('#', '');
        highlightColor = Color(int.parse('FF$hexColor', radix: 16));
      } catch (_) {
        highlightColor = const Color(0xFFF9D71C); // Default yellow
      }
    } else {
      highlightColor = const Color(0xFFF9D71C); // Default yellow
    }

    return HighlightSegment(HighlightData(text: text, color: highlightColor));
  }
}
