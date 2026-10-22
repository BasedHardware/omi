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

  Future<Map<String, List<(double, double)>>> _read({bool serverReachable = true}) async {
    try {
      final file = File('${(await directory()).path}/watch_live_coverage.json');
      if (!await file.exists()) return {};
      final raw = await file.readAsString();
      final decoded =
          await offUiIsolate(() => jsonDecode(raw) as Map<String, dynamic>, size: raw.length, threshold: 16 * 1024);
      final cutoff = _now().millisecondsSinceEpoch / 1000 - ttl.inSeconds;
      // Version 1 counted transport sends as proof; never trust it for deletion.
      if (decoded['version'] != 2) return {};
      final buckets = decoded[serverReachable ? 'reachable' : 'durable'] as Map<String, dynamic>;
      return buckets.map((owner, value) => MapEntry(
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

  Future<void> record(String owner, double start, double end, {required bool serverReachable}) =>
      recordMany([(owner, start, end, serverReachable)]);

  Future<void> recordMany(List<(String, double, double, bool)> records) {
    final work = _tail.then((_) async {
      if (records.isEmpty) return;
      final payload = <String, dynamic>{'version': 2};
      for (final reachable in [false, true]) {
        final all = await _read(serverReachable: reachable);
        final cutoff = _now().millisecondsSinceEpoch / 1000 - ttl.inSeconds;
        for (final record in records) {
          final (owner, start, end, canReachServer) = record;
          if (owner.isEmpty || end <= start || end <= cutoff || (reachable && !canReachServer)) continue;
          all.putIfAbsent(owner, () => []).add((max(start, cutoff), end));
        }
        for (final owner in all.keys.toList()) {
          final ranges = all[owner]!..sort((a, b) => a.$1.compareTo(b.$1));
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
        }
        payload[reachable ? 'reachable' : 'durable'] =
            all.map((k, v) => MapEntry(k, v.map((r) => [r.$1, r.$2]).toList()));
      }
      final file = File('${(await directory()).path}/watch_live_coverage.json');
      final tmp = File('${file.path}.tmp');
      final encoded =
          await offUiIsolate(() => jsonEncode(payload), size: payload.toString().length, threshold: 16 * 1024);
      await tmp.writeAsString(encoded, flush: true);
      await tmp.rename(file.path);
    });
    _tail = work.catchError((_) {});
    return work;
  }

  Future<bool> covers(String owner, double start, double end, {bool serverReachable = true}) async {
    await _tail;
    if (end <= start) return false;
    final ranges = (await _read(serverReachable: serverReachable))[owner] ?? [];
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
