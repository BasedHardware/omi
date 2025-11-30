import 'package:flutter/material.dart';
import 'models/rich_list_item_data.dart';
import 'models/pie_chart_data.dart';
import 'models/accordion_data.dart';
import 'parsers/parsers.dart';

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

/// A segment containing chart data (can be rendered as pie, donut, or bar chart)
class PieChartSegment extends ContentSegment {
  final PieChartDisplayData data;

  const PieChartSegment(this.data);
}

/// A segment containing an accordion with expandable sections
class AccordionSegment extends ContentSegment {
  final AccordionDisplayData data;

  const AccordionSegment(this.data);
}

/// Main parser for extracting custom XML tags from markdown content.
///
/// Uses modular [BaseTagParser] implementations for each tag type.
/// To add a new tag type:
/// 1. Create a new parser class extending [BaseTagParser] in parsers/
/// 2. Create a corresponding [ContentSegment] subclass
/// 3. Register the parser in [_parsers] list
/// 4. Handle the new segment type in GenerativeMarkdownWidget
class XmlTagParser {
  /// List of registered tag parsers
  /// Add new parsers here to extend functionality
  final List<BaseTagParser> _parsers = [
    RichListParser(),
    ChartParser(),
    AccordionParser(),
  ];

  /// Check if content contains any generative UI tags
  static bool containsGenerativeTags(String content) {
    return RichListParser().containsTag(content) ||
        ChartParser().containsTag(content) ||
        AccordionParser().containsTag(content);
  }

  /// Parse content into a list of segments (markdown and widgets)
  List<ContentSegment> parse(String content) {
    if (!containsGenerativeTags(content)) {
      return [MarkdownSegment(content)];
    }

    final segments = <ContentSegment>[];
    final matches = <_TagMatch>[];

    // Collect all matches from all parsers
    for (final parser in _parsers) {
      for (final match in parser.findMatches(content)) {
        matches.add(_TagMatch(
          start: match.start,
          end: match.end,
          match: match,
          parser: parser,
        ));
      }
    }

    // Sort matches by position
    matches.sort((a, b) => a.start.compareTo(b.start));

    // Process content sequentially
    int currentIndex = 0;

    for (final tagMatch in matches) {
      // Add markdown content before this match
      if (tagMatch.start > currentIndex) {
        final markdownContent = content.substring(currentIndex, tagMatch.start).trim();
        if (markdownContent.isNotEmpty) {
          segments.add(MarkdownSegment(markdownContent));
        }
      }

      // Parse and add the widget segment
      try {
        final segment = tagMatch.parser.parse(tagMatch.match);
        if (segment != null) {
          segments.add(segment);
        }
      } catch (e) {
        // On parse error, treat as markdown
        debugPrint('Error parsing generative UI tag: $e');
        final rawContent = content.substring(tagMatch.start, tagMatch.end);
        segments.add(MarkdownSegment(rawContent));
      }

      currentIndex = tagMatch.end;
    }

    // Add remaining markdown content
    if (currentIndex < content.length) {
      final remainingContent = content.substring(currentIndex).trim();
      if (remainingContent.isNotEmpty) {
        segments.add(MarkdownSegment(remainingContent));
      }
    }

    return segments;
  }
}

/// Internal class to track tag matches with their parser
class _TagMatch {
  final int start;
  final int end;
  final RegExpMatch match;
  final BaseTagParser parser;

  const _TagMatch({
    required this.start,
    required this.end,
    required this.match,
    required this.parser,
  });
}
