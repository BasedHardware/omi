import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:markdown/markdown.dart' as md;

import 'package:nooto_v2/theme/app_theme.dart';
import 'highlight_widget.dart';

/// Custom inline syntax for parsing highlight markers in markdown.
/// Converts `==text==` or `==color:text==` into an Element with highlight tag.
class HighlightSyntax extends md.InlineSyntax {
  HighlightSyntax() : super(r'==([a-zA-Z]+):([^=]+)==|==([^=:]+)==');

  @override
  bool onMatch(md.InlineParser parser, Match match) {
    String color;
    String text;

    if (match.group(1) != null) {
      color = match.group(1)!;
      text = match.group(2)?.trim() ?? '';
    } else {
      color = 'yellow';
      text = match.group(3)?.trim() ?? '';
    }

    if (text.isEmpty) return false;

    final element = md.Element.text('highlight', text);
    element.attributes['color'] = color;
    parser.addNode(element);
    return true;
  }
}

/// Custom builder to render highlight elements with the flat-tint effect.
class HighlightBuilder extends MarkdownElementBuilder {
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
  bool isBlockElement() => false;

  @override
  Widget visitElementAfter(md.Element element, TextStyle? preferredStyle) {
    final colorName = element.attributes['color'] ?? 'yellow';
    final color = _namedColors[colorName.toLowerCase()] ?? _namedColors['yellow']!;

    return MarkerHighlight(
      color: color,
      verticalPadding: 1.0,
      horizontalPadding: 3.0,
      child: Text(
        element.textContent,
        style: (preferredStyle ?? const TextStyle(fontSize: 16)).copyWith(
          fontWeight: FontWeight.w500,
          color: AppColors.textPrimary,
        ),
      ),
    );
  }
}
