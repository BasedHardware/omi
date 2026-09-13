/// User-facing math for offline sync / upload progress.
///
/// Progress must read as **completed** (0% → 100%), never remaining.
/// Counters must read as **processed/total** (e.g. 25/100), never negative
/// or a single-file denominator when many recordings are queued.
class OfflineProcessingDisplay {
  const OfflineProcessingDisplay._();

  /// Normalizes raw [current] and [total] into a completed count and total.
  ///
  /// [current] is treated as a 0-based number of finished items when non-negative.
  /// Legacy callers sometimes passed a negative "remaining" offset; when
  /// [current] is negative and [total] > 1, we recover completed as
  /// `total + current` (e.g. -75 of 100 → 25 done).
  static ({int processed, int total}) normalizeCounts({required int current, required int total}) {
    if (total <= 0) {
      return (processed: 0, total: 0);
    }

    var processed = current;
    if (processed < 0 && total > 1) {
      processed = total + processed;
    }
    if (processed < 0) {
      processed = 0;
    }
    if (processed > total) {
      processed = total;
    }
    return (processed: processed, total: total);
  }

  /// Completion percentage in 0–100 (never inverted remaining).
  static int completionPercent({required int processed, required int total}) {
    final normalized = normalizeCounts(current: processed, total: total);
    if (normalized.total <= 0) {
      return 0;
    }
    return ((normalized.processed / normalized.total) * 100).round().clamp(0, 100);
  }

  /// Fraction in 0.0–1.0 for progress bars.
  static double completionFraction({required int processed, required int total}) {
    final normalized = normalizeCounts(current: processed, total: total);
    if (normalized.total <= 0) {
      return 0;
    }
    return (normalized.processed / normalized.total).clamp(0.0, 1.0);
  }
}
