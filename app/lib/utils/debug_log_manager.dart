import 'dart:async';
import 'dart:convert';
import 'dart:io';
// no random file names; we use date-based naming and prune by age

import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:omi/backend/preferences.dart';

/// Lightweight debug log manager to persist important diagnostics when
/// developer debug logging is enabled.
class DebugLogManager {
  DebugLogManager._();

  static String _dailyFileName() {
    final d = DateTime.now().toUtc();
    final y = d.year.toString().padLeft(4, '0');
    final m = d.month.toString().padLeft(2, '0');
    final day = d.day.toString().padLeft(2, '0');
    return 'omi_debug_$y$m$day.log';
  }
  static const int _maxFileBytes = 5 * 1024 * 1024; // 5MB cap

  static File? _file;
  static final DateFormat _ts = DateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'");
  static bool _initializing = false;
  static bool _prunedOnce = false;

  static bool get isEnabled => SharedPreferencesUtil().devLogsToFileEnabled;

  static Future<File> _ensureFile() async {
    if (_file != null) return _file!;
    if (_initializing) {
      // Wait briefly if concurrent init
      for (int i = 0; i < 10 && _file == null; i++) {
        await Future.delayed(const Duration(milliseconds: 50));
      }
      if (_file != null) return _file!;
    }
    _initializing = true;
    try {
      final dir = await getApplicationDocumentsDirectory();
      if (!_prunedOnce) {
        await _pruneOldLogs(retainDays: 3);
        _prunedOnce = true;
      }
      final f = File('${dir.path}/${_dailyFileName()}');
      if (!(await f.exists())) {
        await f.create(recursive: true);
      }
      _file = f;
      return f;
    } finally {
      _initializing = false;
    }
  }

  static Future<File?> getLogFile() async {
    try {
      return await _ensureFile();
    } catch (_) {
      return null;
    }
  }

  static Future<void> setEnabled(bool enabled) async {
    SharedPreferencesUtil().devLogsToFileEnabled = enabled;
    if (!enabled) return;
    await _ensureFile();
    await _pruneOldLogs(retainDays: 3);
  }

  static String _timestamp() => _ts.format(DateTime.now().toUtc());

  static Future<void> _rotateIfNeeded(File f) async {
    try {
      final len = await f.length();
      if (len <= _maxFileBytes) return;
      // Simple rotation: delete old file
      await f.writeAsString('', mode: FileMode.write, flush: true);
    } catch (_) {}
  }

  static Future<void> _append(String line) async {
    if (!isEnabled) return;
    try {
      final f = await _ensureFile();
      await _rotateIfNeeded(f);
      await f.writeAsString('$line\n', mode: FileMode.append, flush: false);
    } catch (_) {
      // Swallow to avoid impacting app flow
    }
  }

  static Future<void> clear() async {
    try {
      final f = await _ensureFile();
      await f.writeAsString('', mode: FileMode.write, flush: true);
    } catch (_) {}
  }

  /// Returns available debug log files (within retention), sorted newest first.
  static Future<List<File>> listLogFiles() async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final files = <File>[];
      await for (final entity in Directory(dir.path).list(followLinks: false)) {
        if (entity is! File) continue;
        final name = entity.uri.pathSegments.isNotEmpty ? entity.uri.pathSegments.last : '';
        if (!name.startsWith('omi_debug_') || !name.endsWith('.log')) continue;
        files.add(entity);
      }
      // Sort by filename descending (YYYYMMDD ensures lexical order = chronological),
      // fallback to lastModified if names differ.
      files.sort((a, b) {
        final an = a.uri.pathSegments.last;
        final bn = b.uri.pathSegments.last;
        final cmp = bn.compareTo(an);
        return cmp != 0 ? cmp : 0;
      });
      return files;
    } catch (_) {
      return const <File>[];
    }
  }

  static Future<void> _pruneOldLogs({int retainDays = 3}) async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final now = DateTime.now().toUtc();
      final stream = Directory(dir.path).list(followLinks: false);
      await for (final entity in stream) {
        if (entity is! File) continue;
        final name = entity.uri.pathSegments.isNotEmpty ? entity.uri.pathSegments.last : '';
        if (!name.startsWith('omi_debug_') || !name.endsWith('.log')) continue;
        // Expect format omi_debug_YYYYMMDD.log
        final datePart = name.replaceAll('omi_debug_', '').replaceAll('.log', '');
        if (datePart.length != 8) continue;
        final y = int.tryParse(datePart.substring(0, 4));
        final m = int.tryParse(datePart.substring(4, 6));
        final d = int.tryParse(datePart.substring(6, 8));
        if (y == null || m == null || d == null) continue;
        final fileDate = DateTime.utc(y, m, d);
        final age = now.difference(fileDate).inDays;
        if (age > retainDays) {
          try {
            await entity.delete();
          } catch (_) {}
        }
      }
    } catch (_) {}
  }

  static Future<void> logError(Object error, [StackTrace? stack, String? message, Map<String, Object?> extra = const {}]) async {
    final payload = <String, Object?>{
      'ts': _timestamp(),
      'level': 'ERROR',
      'message': message ?? error.toString(),
      if (stack != null) 'stack': stack.toString(),
      if (extra.isNotEmpty) 'extra': extra,
    };
    await _append(jsonEncode(payload));
  }

  static Future<void> logWarning(String message, [Map<String, Object?> extra = const {}]) async {
    final payload = <String, Object?>{
      'ts': _timestamp(),
      'level': 'WARN',
      'message': message,
      if (extra.isNotEmpty) 'extra': extra,
    };
    await _append(jsonEncode(payload));
  }

  static Future<void> logInfo(String message, [Map<String, Object?> extra = const {}]) async {
    final payload = <String, Object?>{
      'ts': _timestamp(),
      'level': 'INFO',
      'message': message,
      if (extra.isNotEmpty) 'extra': extra,
    };
    await _append(jsonEncode(payload));
  }

  /// Logs a structured diagnostic event (e.g., device/transcription connection changes)
  static Future<void> logEvent(String type, Map<String, Object?> fields) async {
    final payload = <String, Object?>{
      'timestamp': _timestamp(),
      'level': 'EVENT',
      'type': type,
      ...fields,
    };
    await _append(jsonEncode(payload));
  }
}


