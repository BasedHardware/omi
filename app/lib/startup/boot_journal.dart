import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// Bounded, privacy-safe startup history. Diagnostic I/O must never stop boot.
class BootJournal {
  BootJournal({Future<Directory> Function()? documents}) : _documents = documents ?? getApplicationDocumentsDirectory;

  static final BootJournal instance = BootJournal();
  static const capacity = 24;
  final Future<Directory> Function() _documents;
  Future<void> _writes = Future<void>.value();
  String? currentStage;
  String? failingStage;

  Future<File> _file() async => File('${(await _documents()).path}/boot_stages.json');

  Future<List<Map<String, dynamic>>> read() async {
    try {
      await _writes;
      final file = await _file();
      if (!await file.exists()) return [];
      final decoded = jsonDecode(await file.readAsString());
      if (decoded is! List) return [];
      return decoded.whereType<Map>().map((row) => Map<String, dynamic>.from(row)).toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> record(String stage, String state, {Object? error}) {
    if (state == 'begin') {
      currentStage = stage;
      failingStage = null;
    }
    if (state == 'failed') failingStage = stage;
    final write = _writes.then((_) async {
      final file = await _file();
      List<Map<String, dynamic>> history = [];
      if (await file.exists()) {
        try {
          final decoded = jsonDecode(await file.readAsString());
          if (decoded is List) {
            history = decoded.whereType<Map>().map((row) => Map<String, dynamic>.from(row)).toList();
          }
        } catch (_) {
          // A torn diagnostic file is replaceable; product state is untouched.
        }
      }
      history.add({
        'stage': stage,
        'state': state,
        'error_type': error?.runtimeType.toString(),
        'at_ms': DateTime.now().millisecondsSinceEpoch,
      });
      if (history.length > capacity) {
        final lastBootBegin = history.lastIndexWhere((row) => row['stage'] == 'boot' && row['state'] == 'begin');
        final tail = history.sublist(history.length - capacity + 1);
        // Keep the boot boundary even when a long startup fills the bounded journal.
        history = lastBootBegin >= 0 && lastBootBegin < history.length - capacity + 1
            ? [history[lastBootBegin], ...tail]
            : history.sublist(history.length - capacity);
      }
      final temporary = File('${file.path}.tmp');
      await temporary.writeAsString(jsonEncode(history), flush: true);
      await temporary.rename(file.path);
    });
    _writes = write.catchError((Object _) {});
    return _writes;
  }

  Future<T> stage<T>(String name, Future<T> Function() operation) async {
    await record(name, 'begin');
    try {
      final result = await operation();
      await record(name, 'completed');
      return result;
    } catch (error) {
      await record(name, 'failed', error: error);
      rethrow;
    }
  }

  /// Last entries are safe for Crashlytics: no exception message or stack.
  Future<String> breadcrumbs() async => jsonEncode(await read());

  /// The most recent failed stage survives later telemetry records.
  String get failureStage => failingStage ?? currentStage ?? 'before_stages';
}
