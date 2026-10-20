class ConversationDateQuery {
  const ConversationDateQuery({required this.query, this.startDate, this.endDate, this.matchedPhrase});

  final String query;
  final DateTime? startDate;
  final DateTime? endDate;
  final String? matchedPhrase;

  bool get hasDateFilter => startDate != null && endDate != null;
}

class _Match {
  _Match(this.start, this.end, this.startDate, this.endDate);

  final int start;
  final int end;
  final DateTime startDate;
  final DateTime endDate;

  int get length => end - start;
}

const _months = <String, int>{
  'january': 1,
  'jan': 1,
  'february': 2,
  'feb': 2,
  'march': 3,
  'mar': 3,
  'april': 4,
  'apr': 4,
  'may': 5,
  'june': 6,
  'jun': 6,
  'july': 7,
  'jul': 7,
  'august': 8,
  'aug': 8,
  'september': 9,
  'sept': 9,
  'sep': 9,
  'october': 10,
  'oct': 10,
  'november': 11,
  'nov': 11,
  'december': 12,
  'dec': 12,
};

const _weekdays = <String, int>{
  'monday': 1,
  'tuesday': 2,
  'wednesday': 3,
  'thursday': 4,
  'friday': 5,
  'saturday': 6,
  'sunday': 7,
};

const _monthToken =
    '(?:january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sept|sep|october|oct|november|nov|december|dec)';
const _weekdayToken = '(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)';
const _maxDaysAgo = 3660;
// "on"/"in" immediately before a date phrase, e.g. "meetings in march".
final _qualifierRe = RegExp(r'(?:^|\s)(on|in)\s+$', caseSensitive: false);

DateTime? _validDay(int year, int month, int day) {
  if (year <= 0) return null;
  final date = DateTime(year, month, day);
  if (date.year != year || date.month != month || date.day != day) return null;
  return date;
}

({DateTime start, DateTime end})? _dayRange(int year, int month, int day) {
  final start = _validDay(year, month, day);
  if (start == null) return null;
  return _dayRangeAt(start);
}

({DateTime start, DateTime end}) _dayRangeAt(DateTime start) =>
    (start: start, end: DateTime(start.year, start.month, start.day + 1).subtract(const Duration(microseconds: 1)));

({DateTime start, DateTime end}) _monthRange(int year, int month) =>
    (start: DateTime(year, month), end: DateTime(year, month + 1).subtract(const Duration(microseconds: 1)));

String _normalize(String input) => input.replaceAll(RegExp(r'\s+'), ' ').trim();

ConversationDateQuery parseConversationDateQuery(String input, {DateTime? now}) {
  final nowLocal = (now ?? DateTime.now()).toLocal();
  final today = DateTime(nowLocal.year, nowLocal.month, nowLocal.day);
  final candidates = <_Match>[];
  final blocked = <(int, int)>[];

  void scan(RegExp re, ({DateTime start, DateTime end})? Function(Match m) build) {
    for (final m in re.allMatches(input)) {
      final range = build(m);
      if (range != null) {
        candidates.add(_Match(m.start, m.end, range.start, range.end));
      } else {
        blocked.add((m.start, m.end));
      }
    }
  }

  scan(RegExp(r'(?<!\w)today(?!\w)', caseSensitive: false), (_) => _dayRange(today.year, today.month, today.day));
  scan(RegExp(r'(?<!\w)yesterday(?!\w)', caseSensitive: false),
      (_) => _dayRangeAt(DateTime(today.year, today.month, today.day - 1)));
  scan(RegExp(r'(?<!\w)last week(?!\w)', caseSensitive: false), (_) {
    final monday = DateTime(today.year, today.month, today.day - (today.weekday - 1 + 7));
    return (
      start: monday,
      end: DateTime(monday.year, monday.month, monday.day + 7).subtract(const Duration(microseconds: 1)),
    );
  });
  scan(RegExp(r'(?<!\w)(\d{1,5}) days? ago(?!\w)', caseSensitive: false), (m) {
    final days = int.parse(m.group(1)!);
    if (days <= 0 || days > _maxDaysAgo) return null;
    return _dayRangeAt(DateTime(today.year, today.month, today.day - days));
  });
  scan(RegExp('(?<!\\w)last ($_weekdayToken)(?!\\w)', caseSensitive: false), (m) {
    final target = _weekdays[m.group(1)!.toLowerCase()]!;
    var delta = (today.weekday - target) % DateTime.daysPerWeek;
    if (delta == 0) delta = DateTime.daysPerWeek;
    return _dayRangeAt(DateTime(today.year, today.month, today.day - delta));
  });
  scan(RegExp('(?<!\\w)$_weekdayToken(?!\\w)', caseSensitive: false), (m) {
    final target = _weekdays[m.group(0)!.toLowerCase()]!;
    final delta = (today.weekday - target) % DateTime.daysPerWeek;
    return _dayRangeAt(DateTime(today.year, today.month, today.day - delta));
  });
  scan(RegExp('(?<!\\w)($_monthToken)\\s*(\\d{1,2})(?:\\s*,?\\s*(\\d{4}))?(?!\\w)', caseSensitive: false), (m) {
    final month = _months[m.group(1)!.toLowerCase()]!;
    final day = int.parse(m.group(2)!);
    final year = m.group(3) != null ? int.parse(m.group(3)!) : today.year;
    return _dayRange(year, month, day);
  });
  scan(
      RegExp('(?<!\\w)(\\d{1,2})(?:st|nd|rd|th)?\\s*($_monthToken)(?:\\s*,?\\s*(\\d{4}))?(?!\\w)',
          caseSensitive: false), (m) {
    final day = int.parse(m.group(1)!);
    final month = _months[m.group(2)!.toLowerCase()]!;
    final year = m.group(3) != null ? int.parse(m.group(3)!) : today.year;
    return _dayRange(year, month, day);
  });
  scan(RegExp('(?<!\\w)($_monthToken)\\s+(\\d{4})(?!\\w)', caseSensitive: false), (m) {
    final month = _months[m.group(1)!.toLowerCase()]!;
    final year = int.parse(m.group(2)!);
    if (year <= 0) return null;
    return _monthRange(year, month);
  });
  // A bare month word is ambiguous: "may I change my address" and "march
  // planning notes" are ordinary searches, not May/March filters. Only treat a
  // bare month as a date when it is the whole query or carries an explicit
  // on/in qualifier. Month/day and month/year forms above stay unconditional.
  final bareMonth = RegExp('(?<!\\w)($_monthToken)(?!\\w)', caseSensitive: false);
  for (final m in bareMonth.allMatches(input)) {
    final month = _months[m.group(0)!.toLowerCase()];
    if (month == null) continue;
    final isEntireQuery = _normalize(input).toLowerCase() == m.group(0)!.toLowerCase();
    final hasQualifier = _qualifierRe.hasMatch(input.substring(0, m.start));
    if (!isEntireQuery && !hasQualifier) continue;
    final range = _monthRange(today.year, month);
    candidates.add(_Match(m.start, m.end, range.start, range.end));
  }
  scan(RegExp(r'(?<![\w/])(\d{1,2})/(\d{1,2})(?:/(\d{4}))?(?![\w/])', caseSensitive: false), (m) {
    final month = int.parse(m.group(1)!);
    final day = int.parse(m.group(2)!);
    final year = m.group(3) != null ? int.parse(m.group(3)!) : today.year;
    return _dayRange(year, month, day);
  });

  candidates.removeWhere((c) => blocked.any((b) => c.start < b.$2 && b.$1 < c.end));
  if (candidates.isEmpty) {
    return ConversationDateQuery(query: _normalize(input));
  }
  candidates.sort((a, b) => b.length != a.length ? b.length.compareTo(a.length) : a.start.compareTo(b.start));
  final match = candidates.first;
  var cutStart = match.start;
  final prefix = input.substring(0, match.start);
  final qualifier = _qualifierRe.firstMatch(prefix);
  if (qualifier != null) cutStart = qualifier.start;
  final stripped = _normalize(input.substring(0, cutStart) + input.substring(match.end));
  return ConversationDateQuery(
    query: stripped,
    startDate: match.startDate,
    endDate: match.endDate,
    matchedPhrase: input.substring(match.start, match.end),
  );
}
