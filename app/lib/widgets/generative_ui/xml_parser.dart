import 'package:flutter/material.dart';
import 'models/rich_list_item_data.dart';
import 'models/pie_chart_data.dart';

/// Base class for parsed content segments
abstract class ContentSegment {
  const ContentSegment();
}

/// A segment containing regular markdown content
class MarkdownSegment extends ContentSegment {
  final String content;

  const MarkdownSegment(this.content);
}

/// A segment containing a rich list
class RichListSegment extends ContentSegment {
  final List<RichListItemData> items;

  const RichListSegment(this.items);
}

/// A segment containing a pie chart
class PieChartSegment extends ContentSegment {
  final PieChartDisplayData data;

  const PieChartSegment(this.data);
}

/// Parser for extracting custom XML tags from markdown content
class XmlTagParser {
  // Pattern to match <rich-list>...</rich-list> blocks
  static final _richListPattern = RegExp(
    r'<rich-list\s*>([\s\S]*?)</rich-list>',
    caseSensitive: false,
  );

  // Pattern to match <pie-chart ...>...</pie-chart> blocks
  static final _pieChartPattern = RegExp(
    r'<pie-chart([^>]*)>([\s\S]*?)</pie-chart>',
    caseSensitive: false,
  );

  // Pattern to match <item .../> tags within rich-list
  // Properly handles quoted attributes containing special characters like URLs
  static final _itemPattern = RegExp(
    r'<item\s+((?:[^>"]*|"[^"]*")+)\s*\/?>',
    caseSensitive: false,
  );

  // Pattern to match <segment .../> tags within pie-chart
  static final _segmentPattern = RegExp(
    r'<segment\s+((?:[^>"]*|"[^"]*")+)\s*\/?>',
    caseSensitive: false,
  );

  // Pattern to parse key="value" attributes
  static final _attributePattern = RegExp(
    r'(\w+)\s*=\s*"([^"]*)"',
  );

  /// Check if content contains any generative UI tags
  static bool containsGenerativeTags(String content) {
    return _richListPattern.hasMatch(content) ||
        _pieChartPattern.hasMatch(content);
  }

  /// Parse content into a list of segments
  List<ContentSegment> parse(String content) {
    debugPrint('=== XmlTagParser.parse() ===');
    debugPrint('Raw content length: ${content.length}');
    debugPrint('Raw content preview: ${content.substring(0, content.length.clamp(0, 500))}...');

    if (!containsGenerativeTags(content)) {
      debugPrint('No generative tags found, returning as single markdown segment');
      return [MarkdownSegment(content)];
    }

    debugPrint('Generative tags found, parsing...');
    final segments = <ContentSegment>[];
    final matches = <_TagMatch>[];

    // Find all rich-list matches
    for (final match in _richListPattern.allMatches(content)) {
      matches.add(_TagMatch(
        start: match.start,
        end: match.end,
        type: _TagType.richList,
        innerContent: match.group(1) ?? '',
        attributes: '',
      ));
    }

    // Find all pie-chart matches
    for (final match in _pieChartPattern.allMatches(content)) {
      matches.add(_TagMatch(
        start: match.start,
        end: match.end,
        type: _TagType.pieChart,
        attributes: match.group(1) ?? '',
        innerContent: match.group(2) ?? '',
      ));
    }

    // Sort matches by position
    matches.sort((a, b) => a.start.compareTo(b.start));

    // Process content sequentially
    int currentIndex = 0;

    debugPrint('Found ${matches.length} tag matches');

    for (final match in matches) {
      debugPrint('Processing match at ${match.start}-${match.end}, type: ${match.type}');

      // Add markdown content before this match
      if (match.start > currentIndex) {
        final markdownContent = content.substring(currentIndex, match.start).trim();
        if (markdownContent.isNotEmpty) {
          debugPrint('--- MARKDOWN SEGMENT BEFORE TAG ---');
          debugPrint('Content ($currentIndex to ${match.start}): "$markdownContent"');
          debugPrint('--- END MARKDOWN SEGMENT ---');
          segments.add(MarkdownSegment(markdownContent));
        }
      }

      // Add the widget segment
      try {
        final segment = _parseTagMatch(match);
        if (segment != null) {
          debugPrint('Added widget segment: ${segment.runtimeType}');
          segments.add(segment);
        }
      } catch (e) {
        // On parse error, treat as markdown
        debugPrint('Error parsing generative UI tag: $e');
        final rawContent = content.substring(match.start, match.end);
        segments.add(MarkdownSegment(rawContent));
      }

      currentIndex = match.end;
    }

    // Add remaining markdown content
    if (currentIndex < content.length) {
      final remainingContent = content.substring(currentIndex).trim();
      if (remainingContent.isNotEmpty) {
        debugPrint('--- MARKDOWN SEGMENT AFTER LAST TAG ---');
        debugPrint('Remaining content: "$remainingContent"');
        debugPrint('--- END REMAINING SEGMENT ---');
        segments.add(MarkdownSegment(remainingContent));
      }
    }

    debugPrint('Total segments created: ${segments.length}');
    for (int i = 0; i < segments.length; i++) {
      final seg = segments[i];
      if (seg is MarkdownSegment) {
        debugPrint('Segment $i: MarkdownSegment - "${seg.content.substring(0, seg.content.length.clamp(0, 100))}..."');
      } else {
        debugPrint('Segment $i: ${seg.runtimeType}');
      }
    }

    return segments;
  }

  ContentSegment? _parseTagMatch(_TagMatch match) {
    switch (match.type) {
      case _TagType.richList:
        return _parseRichList(match.innerContent);
      case _TagType.pieChart:
        return _parsePieChart(match.attributes, match.innerContent);
    }
  }

  RichListSegment? _parseRichList(String innerContent) {
    final items = <RichListItemData>[];

    debugPrint('Parsing rich-list inner content: ${innerContent.substring(0, innerContent.length.clamp(0, 200))}...');

    final matches = _itemPattern.allMatches(innerContent);
    debugPrint('Found ${matches.length} item matches');

    for (final itemMatch in matches) {
      final attributeString = itemMatch.group(1) ?? '';
      debugPrint('Item attributes: $attributeString');
      final attributes = _parseAttributes(attributeString);
      debugPrint('Parsed attributes: $attributes');
      items.add(RichListItemData.fromAttributes(attributes));
    }

    debugPrint('Total items parsed: ${items.length}');
    if (items.isEmpty) return null;
    return RichListSegment(items);
  }

  PieChartSegment? _parsePieChart(String chartAttributes, String innerContent) {
    final attributes = _parseAttributes(chartAttributes);
    final segments = <PieChartSegmentData>[];

    int colorIndex = 0;
    for (final segmentMatch in _segmentPattern.allMatches(innerContent)) {
      final segmentAttrString = segmentMatch.group(1) ?? '';
      final segmentAttrs = _parseAttributes(segmentAttrString);

      // Use default palette color if not specified
      final defaultColor = PieChartDisplayData
          .defaultPalette[colorIndex % PieChartDisplayData.defaultPalette.length];

      segments.add(PieChartSegmentData.fromAttributes(segmentAttrs, defaultColor));
      colorIndex++;
    }

    if (segments.isEmpty) return null;

    return PieChartSegment(PieChartDisplayData(
      title: attributes['title'],
      segments: segments,
      isDonut: attributes['type']?.toLowerCase() == 'donut',
    ));
  }

  Map<String, String> _parseAttributes(String attributeString) {
    final attributes = <String, String>{};

    for (final match in _attributePattern.allMatches(attributeString)) {
      final key = match.group(1);
      final value = match.group(2);
      if (key != null && value != null) {
        attributes[key] = value;
      }
    }

    return attributes;
  }
}

enum _TagType { richList, pieChart }

class _TagMatch {
  final int start;
  final int end;
  final _TagType type;
  final String attributes;
  final String innerContent;

  const _TagMatch({
    required this.start,
    required this.end,
    required this.type,
    required this.attributes,
    required this.innerContent,
  });
}
