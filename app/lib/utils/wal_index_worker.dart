import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:omi/services/wals/wal.dart';

/// Owns serialized index state and all whole-index work off the UI isolate.
/// Requests are serial; success is sent only after flush + atomic rename.
class WalIndexWorker {
  WalIndexWorker._(this._port, this._isolate);
  final SendPort _port;
  final Isolate _isolate;

  static Future<WalIndexWorker> start(String path, {bool seedFromDisk = false}) async {
    final ready = ReceivePort();
    try {
      final isolate =
          await Isolate.spawn(_runIndexWorker, (path, seedFromDisk, ready.sendPort), debugName: 'wal_index_owner');
      final result = await ready.first;
      if (result is! SendPort) {
        isolate.kill(priority: Isolate.immediate);
        throw FileSystemException('WAL index worker startup: $result');
      }
      return WalIndexWorker._(result, isolate);
    } finally {
      ready.close();
    }
  }

  Future<void> apply(Map<int, Map<String, dynamic>> changed, List<int> removed) async {
    final reply = ReceivePort();
    try {
      _port.send((changed, removed, reply.sendPort));
      final error = await reply.first;
      if (error != null) throw FileSystemException('WAL index worker: $error');
    } finally {
      reply.close();
    }
  }

  void close() => _isolate.kill(priority: Isolate.immediate);
}

void _runIndexWorker((String, bool, SendPort) args) async {
  final (path, seedFromDisk, ready) = args;
  final requests = ReceivePort();
  final rows = <int, Map<String, dynamic>>{};
  final file = File(path);
  final backup = File('${file.parent.path}/wals_backup.json');
  if (seedFromDisk) {
    try {
      final source = await file.exists() ? file : backup;
      final decoded = jsonDecode(await source.readAsString()) as Map<String, dynamic>;
      final entries = decoded['wals'] as List;
      for (var i = 0; i < entries.length; i++) {
        rows[i] = Wal.fromJson(Map<String, dynamic>.from(entries[i] as Map)).toJson();
      }
    } catch (error) {
      ready.send(error.toString());
      requests.close();
      return;
    }
  }
  ready.send(requests.sendPort);
  await for (final message in requests) {
    final (changed, removed, reply) = message as (Map<int, Map<String, dynamic>>, List<int>, SendPort);
    // Keep admitted state on write failure: a later retry overwrites these same
    // tokens. No failed delta may silently vanish from a subsequent save.
    rows.addAll(changed);
    for (final token in removed) {
      rows.remove(token);
    }
    try {
      // Best effort backup of the previous *durable* snapshot. Validation and
      // copying also stay on this isolate, including first save after restart.
      try {
        if (await file.exists()) {
          jsonDecode(await file.readAsString());
          final tmp = File('${backup.path}.tmp');
          await file.copy(tmp.path);
          await tmp.rename(backup.path);
        }
      } on FileSystemException catch (_) {
        // A backup failure must not prevent a durable main index write.
      } on FormatException catch (_) {
        // Never replace a good backup with an unreadable main index.
      }
      // A live memory row can become durable after a later admitted disk row.
      // Tokens retain admission order; map insertion order would reorder ties
      // after restart and change the upload queue's stable tie-breaker.
      final orderedTokens = rows.keys.toList()..sort();
      final content = jsonEncode({
        'version': 1,
        'timestamp': DateTime.now().millisecondsSinceEpoch,
        'wals': [for (final token in orderedTokens) rows[token]],
      });
      final tmp = File('$path.tmp');
      await tmp.writeAsString(content, flush: true);
      await tmp.rename(path);
      reply.send(null);
    } catch (error) {
      reply.send(error.toString());
    }
  }
}
