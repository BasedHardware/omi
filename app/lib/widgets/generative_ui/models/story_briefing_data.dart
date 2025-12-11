import 'timeline_data.dart';
import 'quote_board_data.dart';
import 'followups_data.dart';

/// Aggregated data for the journalist story briefing
/// Combines timeline, quotes, and follow-ups into a single cohesive unit
class StoryBriefingData {
  final TimelineDisplayData? timeline;
  final QuoteBoardDisplayData? quoteBoard;
  final FollowupsDisplayData? followups;

  const StoryBriefingData({
    this.timeline,
    this.quoteBoard,
    this.followups,
  });

  bool get hasTimeline => timeline != null && !timeline!.isEmpty;
  bool get hasQuotes => quoteBoard != null && !quoteBoard!.isEmpty;
  bool get hasFollowups => followups != null && !followups!.isEmpty;

  bool get isEmpty => !hasTimeline && !hasQuotes && !hasFollowups;

  int get sectionCount {
    int count = 0;
    if (hasTimeline) count++;
    if (hasQuotes) count++;
    if (hasFollowups) count++;
    return count;
  }

  /// Get a brief summary for the preview card
  String get summary {
    final parts = <String>[];
    if (hasTimeline) {
      parts.add('${timeline!.events.length} events');
    }
    if (hasQuotes) {
      parts.add('${quoteBoard!.quotes.length} quotes');
    }
    if (hasFollowups) {
      parts.add('${followups!.items.length} follow-ups');
    }
    return parts.join(' · ');
  }
}
