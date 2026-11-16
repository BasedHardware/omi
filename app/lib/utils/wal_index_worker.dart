import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:omi/utils/wal_index_codec.dart';

/// Owns serialized index state and all whole-index work off the UI isolate.
/// Requests are serial; success is sent only after flush + atomic rename.
class WalIndexWorker {
  WalIndexWorker._(this._serialize) {
    _events.listen((message) {
      if (message is SendPort) {
        if (!_ready.isCompleted) _ready.complete(message);
      } else if (message is (int, String?)) {
        final (id, error) = message;
        final pending = _pending.remove(id);
        if (error == null) {
          pending?.complete();
        } else {
          pending?.completeError(FileSystemException('WAL index worker: $error'));
        }
      } else {
        // onExit sends null; onError sends [error, stack]. Both are installed
        // by spawn, before the worker can run (including during startup).
        _fail(FileSystemException('WAL index worker terminated: $message'));
      }
    });
  }

  final Future<void> Function(Future<void> Function())? _serialize;
  final _events = ReceivePort();
  final _ready = Completer<SendPort>();
  final _pending = <int, Completer<void>>{};
  late final Isolate _isolate;
  late final SendPort _port;
  FileSystemException? _failure;
  var _nextRequest = 0;

  bool get isDead => _failure != null;

  static Future<WalIndexWorker> start(
    String path, {
    bool seedFromDisk = false,
    String? seedPath,
    Future<void> Function(Future<void> Function())? serialize,
    SendPort? beforeWriteForTesting,
  }) async {
    final worker = WalIndexWorker._(serialize);
    try {
      worker._isolate = await Isolate.spawn(
        _runIndexWorker,
        (path, seedPath ?? (seedFromDisk ? path : null), worker._events.sendPort, beforeWriteForTesting),
        onExit: worker._events.sendPort,
        onError: worker._events.sendPort,
        errorsAreFatal: true,
        debugName: 'wal_index_owner',
      );
    } catch (_) {
      worker._events.close();
      rethrow;
    }
    try {
      worker._port = await worker._ready.future;
      return worker;
    } catch (_) {
      worker.close();
      rethrow;
    }
  }

  void _fail(FileSystemException error) {
    if (_failure != null) return;
    _failure = error;
    if (!_ready.isCompleted) _ready.completeError(error);
    for (final reply in _pending.values) {
      reply.completeError(error);
    }
    _pending.clear();
    _events.close();
  }

  Future<void> apply(Map<int, Map<String, dynamic>> changed, List<int> removed) {
    final serialize = _serialize;
    return serialize == null ? _apply(changed, removed) : serialize(() => _apply(changed, removed));
  }

  Future<void> _apply(Map<int, Map<String, dynamic>> changed, List<int> removed) async {
    if (_failure != null) throw _failure!;
    final id = _nextRequest++;
    final reply = Completer<void>();
    _pending[id] = reply;
    _port.send((id, changed, removed));
    await reply.future;
  }

  /// Killing the isolate also fails outstanding replies via the exit listener.
  void close() => _isolate.kill(priority: Isolate.immediate);
}

void _runIndexWorker((String, String?, SendPort, SendPort?) args) async {
  final (path, seedPath, events, beforeWrite) = args;
  final requests = ReceivePort();
  final rows = <int, Map<String, dynamic>>{};
  final file = File(path);
  final backup = File('${file.parent.path}/wals_backup.json');
  ({int length, DateTime modified})? lastWritten;
  if (seedPath != null) {
    try {
      final source = File(seedPath);
      final invalid = visitWalIndex(await source.readAsString(), (i, wal) => rows[i] = wal.toJson());
      if (invalid) throw const FormatException('invalid_entry');
    } catch (error) {
      events.send('startup: $error');
      requests.close();
      return;
    }
  }
  events.send(requests.sendPort);
  await for (final message in requests) {
    final (id, changed, removed) = message as (int, Map<int, Map<String, dynamic>>, List<int>);
    // Keep admitted state on write failure: a later retry overwrites these same
    // tokens. No failed delta may silently vanish from a subsequent save.
    rows.addAll(changed);
    for (final token in removed) {
      rows.remove(token);
    }
    try {
      if (beforeWrite != null) {
        final resume = ReceivePort();
        beforeWrite.send(resume.sendPort);
        await resume.first;
        resume.close();
      }
      // Best effort backup of the previous *durable* snapshot. Validation and
      // copying also stay on this isolate, including first save after restart.
      try {
        if (await file.exists()) {
          final stat = await file.stat();
          if (lastWritten != (length: stat.size, modified: stat.modified)) {
            if (visitWalIndex(await file.readAsString(), (_, __) {})) {
              throw const FormatException('invalid_entry');
            }
          }
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
      try {
        final stat = await file.stat();
        lastWritten = (length: stat.size, modified: stat.modified);
      } on FileSystemException {
        lastWritten = null; // An unmeasured file must be validated next time.
      }
      events.send((id, null));
    } catch (error) {
      events.send((id, error.toString()));
    }
  }
}
