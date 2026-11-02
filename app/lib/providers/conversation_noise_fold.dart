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
  final Set<DateTime> _revealing = {};
  // Bumped on sign-out/account switch and on "show discarded": a reply for the old state is dropped.
  int _foldGeneration = 0;

  /// Forgets every count, row and reveal (sign-out, account switch, "show discarded" toggled).
  void resetFoldedNoise() {
    _foldGeneration++;
    foldedNoiseCounts = {};
    foldedNoiseByDate = {};
    revealedNoiseDates.clear();
    _revealing.clear();
  }

  /// A clip deleted on this phone leaves its day's fold at once.
  void dropFromFoldedNoise(String conversationId) {
    for (final entry in foldedNoiseByDate.entries) {
      final before = entry.value.length;
      entry.value.removeWhere((c) => c.id == conversationId);
      final count = foldedNoiseCounts[entry.key];
      if (entry.value.length < before && count != null) foldedNoiseCounts[entry.key] = count - 1;
    }
    foldedNoiseCounts.removeWhere((_, count) => count <= 0);
  }

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
    final generation = _foldGeneration;
    Map<DateTime, int>? counts;
    try {
      counts = await (hiddenNoiseCountsFetcherOverride?.call(oldest, end) ??
          getUsageDeviceTimeZone().then((tz) => getHiddenNoiseCounts(start: oldest, end: end, tz: tz)));
    } catch (_) {
      // A background refresh: any failure keeps what Home shows.
      return;
    }
    final fresh = counts;
    if (fresh == null || generation != _foldGeneration) return;
    foldedNoiseCounts = fresh;
    // Rows are re-read on the next reveal, so a clip unhidden or deleted elsewhere does not return.
    foldedNoiseByDate.removeWhere((day, _) => !fresh.containsKey(day) || !revealedNoiseDates.contains(day));
    revealedNoiseDates.removeWhere((day) => !fresh.containsKey(day));
    notifyListeners();
  }

  /// Reveals a day's folded clips in place (fetched on first reveal) or folds them back.
  Future<void> toggleFoldedNoise(DateTime date) async {
    if (revealedNoiseDates.remove(date)) {
      notifyListeners();
      return;
    }
    if (!foldedNoiseByDate.containsKey(date)) {
      if (!_revealing.add(date)) return;
      final generation = _foldGeneration;
      final start = DateTime(date.year, date.month, date.day);
      final end = DateTime(date.year, date.month, date.day, 23, 59, 59);
      List<ServerConversation>? rows;
      try {
        rows = await (foldedNoiseRowsFetcherOverride?.call(start, end) ??
            getConversationsResult(limit: 100, includeDiscarded: true, startDate: start, endDate: end)
                .then((r) => r.ok ? r.items : null));
      } catch (_) {
        rows = null;
      }
      _revealing.remove(date);
      if (rows == null || generation != _foldGeneration) return;
      foldedNoiseByDate[date] = [
        for (final c in rows)
          if (c.isFoldedNoise) c
      ];
    }
    revealedNoiseDates.add(date);
    notifyListeners();
  }
}
