import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// Reliability experiment `vendor_recognizer_on_opened_app`: a local record of what the live-words
/// layer did, one JSON object per line in the app's Documents folder. Counts, times and closed names
/// only: never a word of transcript. It never leaves the phone by itself; a test reads it off the
/// phone over the cable. Bounded: the file starts again when it passes [maxBytes].
class LiveWordsLog {
  LiveWordsLog._();

  static const fileName = 'live_words.log';
  static const maxBytes = 512 * 1024;

  static Future<void> _queue = Future.value();
  static File? _file;
  static bool _unavailable = false;

  static void event(String name, [Map<String, Object?> fields = const {}]) {
    if (_unavailable) return;
    final line = jsonEncode({'t': DateTime.now().toUtc().toIso8601String(), 'event': name, ...fields});
    _queue = _queue.then((_) => _write(line)).catchError((Object _) {
      // No Documents folder (a unit test, a locked phone): the record is optional.
      _unavailable = true;
    });
  }

  static Future<void> _write(String line) async {
    final file = _file ??= File('${(await getApplicationDocumentsDirectory()).path}/$fileName');
    final exists = await file.exists();
    final restart = exists && await file.length() > maxBytes;
    await file.writeAsString('$line\n', mode: restart ? FileMode.write : FileMode.append, flush: false);
  }
}
