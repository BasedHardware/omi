import '../models/story_briefing_data.dart';
import '../models/timeline_data.dart';
import '../models/quote_board_data.dart';
import '../models/followups_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';
import 'timeline_parser.dart';
import 'quote_board_parser.dart';
import 'followups_parser.dart';

/// Parser that aggregates timeline, quote board, and follow-ups into a single
/// Story Briefing component. This prevents multiple journalist components from
/// creating excessive scroll in the chat view.
class StoryBriefingParser extends BaseTagParser {
  final TimelineParser _timelineParser = TimelineParser();
  final QuoteBoardParser _quoteBoardParser = QuoteBoardParser();
  final FollowupsParser _followupsParser = FollowupsParser();

  @override
  bool containsTag(String content) {
    // This parser is special - it detects when multiple journalist
    // components are present and aggregates them
    return _timelineParser.containsTag(content) ||
        _quoteBoardParser.containsTag(content) ||
        _followupsParser.containsTag(content);
  }

  @override
  RegExp get pattern => RegExp(''); // Not used for this parser

  @override
  Iterable<RegExpMatch> findMatches(String content) => [];

  @override
  ContentSegment? parse(RegExpMatch match) => null;

  /// Parse content and aggregate all journalist components into a single briefing
  StoryBriefingData? parseAggregated(String content) {
    TimelineDisplayData? timeline;
    QuoteBoardDisplayData? quoteBoard;
    FollowupsDisplayData? followups;

    // Extract timeline
    for (final match in _timelineParser.findMatches(content)) {
      final segment = _timelineParser.parse(match);
      if (segment is TimelineSegment) {
        timeline = segment.data;
        break; // Take first timeline only
      }
    }

    // Extract quote board
    for (final match in _quoteBoardParser.findMatches(content)) {
      final segment = _quoteBoardParser.parse(match);
      if (segment is QuoteBoardSegment) {
        quoteBoard = segment.data;
        break; // Take first quote board only
      }
    }

    // Extract follow-ups
    for (final match in _followupsParser.findMatches(content)) {
      final segment = _followupsParser.parse(match);
      if (segment is FollowupsSegment) {
        followups = segment.data;
        break; // Take first follow-ups only
      }
    }

    if (timeline == null && quoteBoard == null && followups == null) {
      return null;
    }

    return StoryBriefingData(
      timeline: timeline,
      quoteBoard: quoteBoard,
      followups: followups,
    );
  }

  /// Get the combined range of all journalist tags in the content
  /// Returns (start, end) of the first tag to the last tag
  (int, int)? getCombinedRange(String content) {
    int? firstStart;
    int? lastEnd;

    void updateRange(Iterable<RegExpMatch> matches) {
      for (final match in matches) {
        if (firstStart == null || match.start < firstStart!) {
          firstStart = match.start;
        }
        if (lastEnd == null || match.end > lastEnd!) {
          lastEnd = match.end;
        }
      }
    }

    updateRange(_timelineParser.findMatches(content));
    updateRange(_quoteBoardParser.findMatches(content));
    updateRange(_followupsParser.findMatches(content));

    if (firstStart != null && lastEnd != null) {
      return (firstStart!, lastEnd!);
    }
    return null;
  }
}
