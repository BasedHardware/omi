import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/startup/boot_journal.dart';

/// Forensic copies of stored preferences that failed validation, kept bounded.
///
/// A rejected value is copied to `<key>.corrupt-<microseconds>` and the original removed, so it
/// can be looked at afterwards without the app reading it again. Nothing used to remove a copy:
/// every quarantine left one more behind, in NSUserDefaults / SharedPreferences, which the platform
/// loads in full at startup. On one device a single quarantined cached conversation list was
/// 12.5 MB of a 13.5 MB store, beside six archives of `cachedPeople`.
abstract final class PreferenceQuarantine {
  /// The largest value, in characters of its stored or JSON form, worth an archive. Past it the
  /// quarantine is recorded with the size and the value dropped: these are caches the server refills.
  static const int maxArchivedChars = 64 * 1024;

  /// How long an archive is kept.
  static const Duration retention = Duration(days: 7);

  static const String _marker = '.corrupt-';

  /// Set once [restoreStringLists] has run, so it repairs the damage once and never later.
  static const String restoredMarkerKey = 'quarantineStringListsRestoredV1';

  /// One-shot migrations that consume a list: restoring the list has to re-open them, or the
  /// restored entries are never read. The Limitless migration marked itself done after reading the
  /// queue this bug had just emptied.
  static const Map<String, String> _reopensWhenRestored = {
    'flash_page_pending_uploads': 'limitless_wal_migration_v1',
  };

  /// Puts back string lists that were archived only because they came back from disk untyped
  /// (`List<Object?>`), then prunes. Runs the restore once per install: a list whose newest archive
  /// is a JSON array of strings and whose key is now absent is the state that bug left behind.
  /// Lists holding anything else were genuinely corrupt and stay archived.
  static Future<void> restoreThenPrune(SharedPreferences prefs) async {
    try {
      if (prefs.getBool(restoredMarkerKey) != true) {
        final newest = <String, (int, String)>{};
        for (final archive in prefs.getKeys().where((k) => k.contains(_marker))) {
          final (origin, at) = _parse(archive);
          if (at != null && (newest[origin]?.$1 ?? -1) < at) newest[origin] = (at, archive);
        }
        for (final MapEntry(key: origin, value: (_, archive)) in newest.entries) {
          final raw = prefs.get(archive);
          if (prefs.containsKey(origin) || raw is! String) continue;
          final Object? decoded;
          try {
            decoded = jsonDecode(raw);
          } on FormatException {
            continue;
          }
          if (decoded is! List || !decoded.every((item) => item is String)) continue;
          final list = List<String>.from(decoded);
          if (!await prefs.setStringList(origin, list)) continue;
          await _removeArchivesOf(prefs, origin);
          final reopen = _reopensWhenRestored[origin];
          if (reopen != null && list.isNotEmpty) await prefs.remove(reopen);
          await BootJournal.instance.record('quarantine:$origin', 'restored');
        }
        await prefs.setBool(restoredMarkerKey, true);
      }
    } catch (_) {}
    await prune(prefs);
  }

  /// Removes archives older than [retention], and all but the newest archive of each key. Never
  /// throws: housekeeping must not keep the app from starting.
  static Future<void> prune(SharedPreferences prefs, {DateTime? now}) async {
    try {
      final cutoff = (now ?? DateTime.now()).subtract(retention).microsecondsSinceEpoch;
      final archives = prefs.getKeys().where((k) => k.contains(_marker)).toList();
      final newest = <String, int>{};
      for (final archive in archives) {
        final (origin, at) = _parse(archive);
        if (at != null && (newest[origin] ?? -1) < at) newest[origin] = at;
      }
      var removed = 0;
      for (final archive in archives) {
        final (origin, at) = _parse(archive);
        if (at == null || at < cutoff || newest[origin] != at) {
          await prefs.remove(archive);
          removed++;
        }
      }
      if (removed > 0) await BootJournal.instance.record('quarantine:pruned', '$removed');
    } catch (_) {}
  }

  /// Copies [value] aside as the only archive of [key], then removes [key]. Records the outcome in
  /// the boot journal: [reason], `<reason>_too_large_<chars>`, or `copy_failed` (the original is
  /// then left in place).
  static Future<void> archive(SharedPreferences prefs, String key, Object value, {required String reason}) async {
    try {
      final size = value is String ? value.length : jsonEncode(value).length;
      if (size > maxArchivedChars) {
        await _removeArchivesOf(prefs, key);
        await prefs.remove(key);
        await BootJournal.instance.record('quarantine:$key', '${reason}_too_large_$size');
        return;
      }
      final archive = '$key$_marker${DateTime.now().microsecondsSinceEpoch}';
      bool saved = false;
      if (value is String) saved = await prefs.setString(archive, value);
      if (value is bool) saved = await prefs.setBool(archive, value);
      if (value is int) saved = await prefs.setInt(archive, value);
      if (value is double) saved = await prefs.setDouble(archive, value);
      if (value is List<String>) saved = await prefs.setStringList(archive, value);
      if (value is List && value is! List<String>) saved = await prefs.setString(archive, jsonEncode(value));
      if (saved) {
        // Superseded only once the new copy exists, so a failed write never loses the last one.
        await _removeArchivesOf(prefs, key, except: archive);
        await prefs.remove(key);
      }
      await BootJournal.instance.record('quarantine:$key', saved ? reason : 'copy_failed');
    } catch (_) {
      await BootJournal.instance.record('quarantine:$key', 'copy_failed');
    }
  }

  static Future<void> _removeArchivesOf(SharedPreferences prefs, String key, {String? except}) async {
    for (final existing in prefs.getKeys().where((k) => k.startsWith('$key$_marker') && k != except).toList()) {
      await prefs.remove(existing);
    }
  }

  static (String, int?) _parse(String archive) {
    final i = archive.lastIndexOf(_marker);
    return (archive.substring(0, i), int.tryParse(archive.substring(i + _marker.length)));
  }
}
