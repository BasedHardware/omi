import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/conversation.dart';

/// Home's noise fold (MEDIA_NOISE): per local day, how many clips the server folded away, and the
/// rows themselves once revealed. Home shows one quiet line per day instead of the rows.
mixin ConversationNoiseFold on ChangeNotifier {
  Map<DateTime, List<ServerConversation>> get groupedConversations;
  bool get showDiscardedConversations;

  Map<DateTime, int> foldedNoiseCounts = {};
  Map<DateTime, List<ServerConversation>> foldedNoiseByDate = {};
  final Set<DateTime> revealedNoiseDates = {};

  @visibleForTesting
  Future<Map<DateTime, int>?> Function(DateTime start, DateTime end)? hiddenNoiseCountsFetcherOverride;
  @visibleForTesting
  Future<List<ServerConversation>?> Function(DateTime start, DateTime end)? foldedNoiseRowsFetcherOverride;

  /// Refreshes the counts for the days the list loaded (at most the newest 31). With "show
  /// discarded" on, discarded rows are already on the list, so nothing folds.
  Future<void> refreshFoldedNoiseCounts() async {
    final days = groupedConversations.keys.toList()..sort();
    if (showDiscardedConversations || days.isEmpty) {
      if (foldedNoiseCounts.isNotEmpty) {
        foldedNoiseCounts = {};
        notifyListeners();
      }
      return;
    }
    final newest = days.last;
    final oldest = days.first.isBefore(newest.subtract(const Duration(days: 30)))
        ? newest.subtract(const Duration(days: 30))
        : days.first;
    final end = DateTime(newest.year, newest.month, newest.day, 23, 59, 59);
    final counts = await (hiddenNoiseCountsFetcherOverride?.call(oldest, end) ??
        getUsageDeviceTimeZone().then((tz) => getHiddenNoiseCounts(start: oldest, end: end, tz: tz)));
    if (counts == null) return;
    foldedNoiseCounts = counts;
    foldedNoiseByDate.removeWhere((day, _) => !counts.containsKey(day));
    revealedNoiseDates.removeWhere((day) => !counts.containsKey(day));
    notifyListeners();
  }

  /// Reveals a day's folded clips in place (fetched on first reveal) or folds them back.
  Future<void> toggleFoldedNoise(DateTime date) async {
    if (revealedNoiseDates.remove(date)) {
      notifyListeners();
      return;
    }
    if (!foldedNoiseByDate.containsKey(date)) {
      final start = DateTime(date.year, date.month, date.day);
      final end = DateTime(date.year, date.month, date.day, 23, 59, 59);
      final rows = await (foldedNoiseRowsFetcherOverride?.call(start, end) ??
          getConversationsResult(limit: 100, includeDiscarded: true, startDate: start, endDate: end)
              .then((r) => r.ok ? r.items : null));
      if (rows == null) return;
      foldedNoiseByDate[date] = [
        for (final c in rows)
          if (c.isFoldedNoise) c
      ];
    }
    revealedNoiseDates.add(date);
    notifyListeners();
  }
}
