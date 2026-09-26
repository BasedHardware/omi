import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/logger.dart';

typedef CaptureGapsFetcher = Future<({List<CalendarCaptureGap> items, bool ok})> Function({
  required DateTime start,
  required DateTime end,
});

/// Owns the capture-gap rows the Conversations list shows: the rows, the loaded
/// date span they belong to, and the in-flight read.
///
/// Refetched only when the loaded span changes. A failed read keeps the rows
/// already on screen and releases the span so the next attempt retries, since
/// an unanswered read is not proof that nothing was missed.
class CaptureGapsController {
  CaptureGapsController({CaptureGapsFetcher? fetchGaps}) : _fetchGaps = fetchGaps ?? getCalendarCaptureGaps;

  final CaptureGapsFetcher _fetchGaps;

  Map<DateTime, List<CalendarCaptureGap>> _gapsByDate = const {};
  String? _loadedSpanKey;
  bool _requestInFlight = false;

  Map<DateTime, List<CalendarCaptureGap>> get gapsByDate => _gapsByDate;

  /// Drops the loaded span so the next [refresh] reads again, for an explicit
  /// user request such as pull to refresh.
  void invalidate() => _loadedSpanKey = null;

  /// Loads the gaps for the span [loadedDays] covers. Returns whether
  /// [gapsByDate] changed, so the caller can rebuild.
  Future<bool> refresh(Iterable<DateTime> loadedDays) async {
    final dates = loadedDays.toList()..sort((a, b) => b.compareTo(a));
    if (dates.isEmpty) {
      _loadedSpanKey = null;
      if (_gapsByDate.isEmpty) return false;
      _gapsByDate = const {};
      return true;
    }

    final oldestDay = dates.last;
    final newestDay = dates.first;
    final spanKey = '${oldestDay.toIso8601String()}|${newestDay.toIso8601String()}';
    if (spanKey == _loadedSpanKey || _requestInFlight) return false;
    _loadedSpanKey = spanKey;
    _requestInFlight = true;
    try {
      final result = await _fetchGaps(
        start: DateTime(oldestDay.year, oldestDay.month, oldestDay.day).toUtc(),
        end: DateTime(newestDay.year, newestDay.month, newestDay.day + 1).toUtc(),
      );
      if (!result.ok) {
        _loadedSpanKey = null;
        Logger.error('capture-gaps refresh failed for $spanKey');
        return false;
      }
      _gapsByDate = groupCaptureGapsByLocalDay(result.items);
      return true;
    } catch (error) {
      _loadedSpanKey = null;
      Logger.error('capture-gaps refresh failed: $error');
      return false;
    } finally {
      _requestInFlight = false;
    }
  }
}
