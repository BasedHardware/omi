import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:omi/utils/off_ui_isolate.dart';

/// Durable, owner-scoped proof that the phone already holds Watch audio.
/// Absence/corruption of proof can only keep a recovery copy, never discard it.
class WatchLiveCoverage {
  WatchLiveCoverage(this.directory, {DateTime Function()? now}) : _now = now ?? DateTime.now;
  final Future<Directory> Function() directory;
  final DateTime Function() _now;
  Future<void> _tail = Future.value();
  static const ttl = Duration(days: 7);

  Future<Map<String, List<(double, double)>>> _read() async {
    try {
      final file = File('${(await directory()).path}/watch_live_coverage.json');
      if (!await file.exists()) return {};
      final raw = await file.readAsString();
      final decoded =
          await offUiIsolate(() => jsonDecode(raw) as Map<String, dynamic>, size: raw.length, threshold: 16 * 1024);
      final cutoff = _now().millisecondsSinceEpoch / 1000 - ttl.inSeconds;
      return decoded.map((owner, value) => MapEntry(
          owner,
          (value as List)
              .map((r) => ((r[0] as num).toDouble(), (r[1] as num).toDouble()))
              .where((r) => r.$2 > cutoff && r.$2 > r.$1)
              .map((r) => (max(r.$1, cutoff), r.$2))
              .toList()));
    } catch (_) {
      return {};
    }
  }

  Future<void> record(String owner, double start, double end) {
    final work = _tail.then((_) async {
      if (owner.isEmpty || end <= start) return;
      final all = await _read();
      final cutoff = _now().millisecondsSinceEpoch / 1000 - ttl.inSeconds;
      final ranges = [...?all[owner], if (end > cutoff) (max(start, cutoff), end)]
        ..sort((a, b) => a.$1.compareTo(b.$1));
      final merged = <(double, double)>[];
      for (final r in ranges) {
        if (merged.isNotEmpty && r.$1 <= merged.last.$2) {
          final last = merged.removeLast();
          merged.add((last.$1, max(last.$2, r.$2)));
        } else {
          merged.add(r);
        }
      }
      all[owner] = merged;
      final file = File('${(await directory()).path}/watch_live_coverage.json');
      final tmp = File('${file.path}.tmp');
      final payload = all.map((k, v) => MapEntry(k, v.map((r) => [r.$1, r.$2]).toList()));
      final encoded = await offUiIsolate(() => jsonEncode(payload),
          size: all.values.fold<int>(0, (n, r) => n + r.length), threshold: 1000);
      await tmp.writeAsString(encoded, flush: true);
      await tmp.rename(file.path);
    });
    _tail = work.catchError((_) {});
    return work;
  }

  Future<bool> covers(String owner, double start, double end) async {
    await _tail;
    if (end <= start) return false;
    final ranges = (await _read())[owner] ?? [];
    ranges.sort((a, b) => a.$1.compareTo(b.$1));
    var covered = 0.0;
    // Re-union on read as well: even a duplicated persisted range cannot
    // manufacture coverage proof for missing audio.
    var frontier = start;
    for (final r in ranges) {
      final lo = max(frontier, max(start, r.$1));
      final hi = min(end, r.$2);
      if (hi > lo) {
        covered += hi - lo;
        frontier = hi;
      }
    }
    return covered / (end - start) >= .95;
  }
}
