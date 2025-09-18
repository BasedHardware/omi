class DateRangeUtc {
  final DateTime? startUtc; // inclusive
  final DateTime? endExclusiveUtc; // exclusive

  const DateRangeUtc({required this.startUtc, required this.endExclusiveUtc});
}

/// Computes a UTC date range for common presets using LOCAL-day anchoring.
/// Presets:
/// 0: All, 1: Today, 2: Yesterday, 3: Last7, 4: Last30
DateRangeUtc computeDateRangeUtc(int preset, {DateTime? nowLocal}) {
  final DateTime localNow = nowLocal ?? DateTime.now();
  final DateTime startOfTodayLocal = DateTime(localNow.year, localNow.month, localNow.day);
  final DateTime startOfTodayUtc = startOfTodayLocal.toUtc();

  switch (preset) {
    case 0: // All
      return const DateRangeUtc(startUtc: null, endExclusiveUtc: null);
    case 1: // Today
      return DateRangeUtc(
        startUtc: startOfTodayUtc,
        endExclusiveUtc: startOfTodayUtc.add(const Duration(days: 1)),
      );
    case 2: // Yesterday
      final DateTime startOfYesterdayUtc = startOfTodayLocal.subtract(const Duration(days: 1)).toUtc();
      return DateRangeUtc(
        startUtc: startOfYesterdayUtc,
        endExclusiveUtc: startOfYesterdayUtc.add(const Duration(days: 1)),
      );
    case 3: // Last 7 days
      final DateTime endExclusive = startOfTodayUtc.add(const Duration(days: 1));
      return DateRangeUtc(
        startUtc: endExclusive.subtract(const Duration(days: 7)),
        endExclusiveUtc: endExclusive,
      );
    case 4: // Last 30 days
      final DateTime endExclusive = startOfTodayUtc.add(const Duration(days: 1));
      return DateRangeUtc(
        startUtc: endExclusive.subtract(const Duration(days: 30)),
        endExclusiveUtc: endExclusive,
      );
    default:
      // Unknown preset: return current values by caller's responsibility
      return DateRangeUtc(startUtc: null, endExclusiveUtc: null);
  }
}
