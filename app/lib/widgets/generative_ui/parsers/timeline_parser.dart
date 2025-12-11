import '../models/timeline_data.dart';
import '../xml_parser.dart';
import 'base_tag_parser.dart';

/// Parser for <timeline> tags containing chronological event elements.
///
/// Example:
/// ```xml
/// <timeline title="Mayor Interview">
///   <event time="10:02" label="Context">Mayor explains recent budget cut</event>
///   <event time="10:15" label="Conflict">Question on police overtime spending</event>
///   <event time="10:27" label="Human impact">Resident story about bus route removal</event>
/// </timeline>
/// ```
class TimelineParser extends BaseTagParser {
  // Pattern to match <timeline ...>...</timeline> blocks
  static final _timelinePattern = RegExp(
    r'<timeline([^>]*)>([\s\S]*?)</timeline>',
    caseSensitive: false,
  );

  // Pattern to match <event ...>...</event> tags within timeline
  static final _eventPattern = RegExp(
    r'<event\s+([^>]*)>([\s\S]*?)</event>',
    caseSensitive: false,
  );

  @override
  RegExp get pattern => _timelinePattern;

  @override
  ContentSegment? parse(RegExpMatch match) {
    final timelineAttributes = match.group(1) ?? '';
    final innerContent = match.group(2) ?? '';
    return _parseTimeline(timelineAttributes, innerContent);
  }

  TimelineSegment? _parseTimeline(String timelineAttributes, String innerContent) {
    final attributes = parseAttributes(timelineAttributes);
    final events = <TimelineEventData>[];

    for (final eventMatch in _eventPattern.allMatches(innerContent)) {
      final eventAttrString = eventMatch.group(1) ?? '';
      final eventContent = eventMatch.group(2) ?? '';
      final eventAttrs = parseAttributes(eventAttrString);

      events.add(TimelineEventData.fromParsed(
        attributes: eventAttrs,
        innerContent: eventContent,
      ));
    }

    if (events.isEmpty) return null;

    return TimelineSegment(TimelineDisplayData(
      title: attributes['title'],
      events: events,
    ));
  }
}
