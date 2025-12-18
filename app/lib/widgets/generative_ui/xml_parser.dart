import 'package:flutter/material.dart';
import 'models/rich_list_item_data.dart';
import 'models/pie_chart_data.dart';
import 'models/accordion_data.dart';
import 'models/timeline_data.dart';
import 'models/quote_board_data.dart';
import 'models/followups_data.dart';
import 'models/story_briefing_data.dart';
import 'models/highlight_data.dart';
import 'models/study_data.dart';
import 'models/task_data.dart';
import 'models/flow_data.dart';
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

/// A segment containing a story timeline
class TimelineSegment extends ContentSegment {
  final TimelineDisplayData data;

  const TimelineSegment(this.data);
}

/// A segment containing a quote board
class QuoteBoardSegment extends ContentSegment {
  final QuoteBoardDisplayData data;

  const QuoteBoardSegment(this.data);
}

/// A segment containing follow-up items
class FollowupsSegment extends ContentSegment {
  final FollowupsDisplayData data;

  const FollowupsSegment(this.data);
}

/// A segment containing an aggregated story briefing (timeline + quotes + follow-ups)
class StoryBriefingSegment extends ContentSegment {
  final StoryBriefingData data;

  const StoryBriefingSegment(this.data);
}

/// A segment containing a highlight
class HighlightSegment extends ContentSegment {
  final HighlightData data;

  const HighlightSegment(this.data);
}

/// A segment containing study mode (flashcards and ABC questions)
class StudySegment extends ContentSegment {
  final StudyData data;

  const StudySegment(this.data);
}

/// A segment containing a single task with steps and transcript references
class TaskSegment extends ContentSegment {
  final TaskData data;

  const TaskSegment(this.data);
}

/// A segment containing a flow/use case with steps
class FlowSegment extends ContentSegment {
  final FlowData data;

  const FlowSegment(this.data);
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
  /// List of registered tag parsers (non-journalist components)
  /// Note: HighlightParser is NOT included here because highlights are inline
  /// elements handled by the markdown renderer, not block-level segments
  final List<BaseTagParser> _baseParsers = [
    RichListParser(),
    ChartParser(),
    AccordionParser(),
    StudyParser(),
    TaskParser(),
    FlowParser(),
  ];

  /// Journalist component parsers (these get aggregated into Story Briefing)
  final TimelineParser _timelineParser = TimelineParser();
  final QuoteBoardParser _quoteBoardParser = QuoteBoardParser();
  final FollowupsParser _followupsParser = FollowupsParser();

  /// Check if content contains any generative UI tags
  static bool containsGenerativeTags(String content) {
    return RichListParser().containsTag(content) ||
        ChartParser().containsTag(content) ||
        AccordionParser().containsTag(content) ||
        StudyParser().containsTag(content) ||
        TaskParser().containsTag(content) ||
        FlowParser().containsTag(content) ||
        TimelineParser().containsTag(content) ||
        QuoteBoardParser().containsTag(content) ||
        FollowupsParser().containsTag(content);
  }

  /// Check if content contains any journalist tags
  bool _containsJournalistTags(String content) {
    return _timelineParser.containsTag(content) ||
        _quoteBoardParser.containsTag(content) ||
        _followupsParser.containsTag(content);
  }

  /// Parse content into a list of segments (markdown and widgets)
  List<ContentSegment> parse(String content) {
    if (!containsGenerativeTags(content)) {
      return [MarkdownSegment(content)];
    }

    final segments = <ContentSegment>[];
    final matches = <_TagMatch>[];

    // Collect matches from base parsers
    for (final parser in _baseParsers) {
      for (final match in parser.findMatches(content)) {
        matches.add(_TagMatch(
          start: match.start,
          end: match.end,
          match: match,
          parser: parser,
        ));
      }
    }

    // Check for journalist components and aggregate them
    final hasJournalistTags = _containsJournalistTags(content);
    int? journalistRangeStart;
    int? journalistRangeEnd;
    StoryBriefingData? briefingData;

    if (hasJournalistTags) {
      // Collect all journalist tag ranges (including preceding section headers)
      final journalistMatches = <(int, int)>[];

      // Helper to find preceding section header and adjust start position
      int findStartWithHeader(int tagStart, String tagContent) {
        final beforeContent = content.substring(0, tagStart);

        // Pattern to match section headers - these should be removed when aggregating
        // Matches standalone lines like "Timeline", "## Quotes", "Follow-ups:", etc.
        final sectionHeaderPattern = RegExp(
          r'(?:^|\n)\s*(#{1,3}\s*)?(Timeline|Quotes?|Quote\s*Board|Follow[\s-]?ups?|Key\s*Tension\s*Points?|Additional\s*Context)[:\s]*$',
          caseSensitive: false,
          multiLine: true,
        );

        final headerMatch = sectionHeaderPattern.allMatches(beforeContent).lastOrNull;
        if (headerMatch != null) {
          // Check if only whitespace between header and tag
          final betweenContent = content.substring(headerMatch.end, tagStart);
          if (betweenContent.trim().isEmpty) {
            // Include the header in the range to remove
            // Start from the newline before the header (if exists)
            return headerMatch.start == 0 ? 0 : headerMatch.start;
          }
        }
        return tagStart;
      }

      for (final match in _timelineParser.findMatches(content)) {
        final start = findStartWithHeader(match.start, content);
        journalistMatches.add((start, match.end));
      }
      for (final match in _quoteBoardParser.findMatches(content)) {
        final start = findStartWithHeader(match.start, content);
        journalistMatches.add((start, match.end));
      }
      for (final match in _followupsParser.findMatches(content)) {
        final start = findStartWithHeader(match.start, content);
        journalistMatches.add((start, match.end));
      }

      if (journalistMatches.isNotEmpty) {
        journalistRangeStart = journalistMatches.map((m) => m.$1).reduce((a, b) => a < b ? a : b);
        journalistRangeEnd = journalistMatches.map((m) => m.$2).reduce((a, b) => a > b ? a : b);

        // Parse each journalist component
        TimelineDisplayData? timeline;
        QuoteBoardDisplayData? quoteBoard;
        FollowupsDisplayData? followups;

        for (final match in _timelineParser.findMatches(content)) {
          final segment = _timelineParser.parse(match);
          if (segment is TimelineSegment) {
            timeline = segment.data;
            break;
          }
        }

        for (final match in _quoteBoardParser.findMatches(content)) {
          final segment = _quoteBoardParser.parse(match);
          if (segment is QuoteBoardSegment) {
            quoteBoard = segment.data;
            break;
          }
        }

        for (final match in _followupsParser.findMatches(content)) {
          final segment = _followupsParser.parse(match);
          if (segment is FollowupsSegment) {
            followups = segment.data;
            break;
          }
        }

        briefingData = StoryBriefingData(
          timeline: timeline,
          quoteBoard: quoteBoard,
          followups: followups,
        );
      }
    }

    // Sort base matches by position
    matches.sort((a, b) => a.start.compareTo(b.start));

    // Process content sequentially
    int currentIndex = 0;
    bool briefingAdded = false;

    for (final tagMatch in matches) {
      // Check if we need to add the briefing before this match
      if (!briefingAdded &&
          briefingData != null &&
          journalistRangeStart != null &&
          tagMatch.start > journalistRangeStart) {
        // Add markdown before journalist section
        if (journalistRangeStart > currentIndex) {
          final markdownContent = content.substring(currentIndex, journalistRangeStart).trim();
          if (markdownContent.isNotEmpty) {
            segments.add(MarkdownSegment(markdownContent));
          }
        }
        // Add the aggregated briefing
        segments.add(StoryBriefingSegment(briefingData));
        briefingAdded = true;
        currentIndex = journalistRangeEnd!;
      }

      // Skip if this match is within the journalist range
      if (journalistRangeStart != null &&
          journalistRangeEnd != null &&
          tagMatch.start >= journalistRangeStart &&
          tagMatch.end <= journalistRangeEnd) {
        continue;
      }

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
        debugPrint('Error parsing generative UI tag: $e');
        final rawContent = content.substring(tagMatch.start, tagMatch.end);
        segments.add(MarkdownSegment(rawContent));
      }

      currentIndex = tagMatch.end;
    }

    // Add briefing if not yet added and there are journalist tags
    if (!briefingAdded && briefingData != null && journalistRangeStart != null) {
      if (journalistRangeStart > currentIndex) {
        final markdownContent = content.substring(currentIndex, journalistRangeStart).trim();
        if (markdownContent.isNotEmpty) {
          segments.add(MarkdownSegment(markdownContent));
        }
      }
      segments.add(StoryBriefingSegment(briefingData));
      currentIndex = journalistRangeEnd!;
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
