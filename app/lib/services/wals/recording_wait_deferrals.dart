import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:omi/backend/preferences.dart';
import 'package:path/path.dart' as path;

/// Paces repeat custody probes for one recording. The WAL ledger owns audio and
/// acknowledgment. This state only controls when the gate can send another POST.
class RecordingWaitDeferrals {
  RecordingWaitDeferrals(this._now, {bool persist = false}) : _prefs = persist ? SharedPreferencesUtil() : null;

  static const maxWaitSeconds = 300;
  static const defaultWaitSeconds = 30;
  static const _maxBaseSeconds = 240; // Leave room for jitter even at the cap.
  static const _streakRetention = Duration(minutes: 30);
  static const _prefKey = 'recordingCustodyWaitsV2';

  final DateTime Function() _now;
  final SharedPreferencesUtil? _prefs;
  final _random = Random();
  final Map<String, ({int deadlineMs, int baseSeconds})> _waits = {};
  String? _owner;

  static String? key({String? recordingGroup, String? filePath}) {
    if (recordingGroup != null) return 'group:$recordingGroup';
    // The server can resolve a recording using its audio interval. Keep that
    // fallback local to the WALs sent in the refusal, without pausing imports.
    if (filePath != null && filePath.isNotEmpty) return 'wal:${path.basename(filePath)}';
    return null;
  }

  // An upload group can include location. Keep raw group identity out of prefs.
  static String _storageKey(String key) => sha256.convert(utf8.encode(key)).toString();

  bool isWaiting(String? key) {
    if (key == null) return false;
    _loadOwner();
    if (_waits.isEmpty) return false;
    final now = _now().millisecondsSinceEpoch;
    final deadline = _waits[_storageKey(key)]?.deadlineMs ?? 0;
    return deadline > now && deadline - now <= maxWaitSeconds * 1000;
  }

  Future<void> defer(Set<String> keys, int? seconds) async {
    if (keys.isEmpty) return;
    _loadOwner();
    final now = _now().millisecondsSinceEpoch;
    _waits.removeWhere((_, wait) => !_validDeadline(wait.deadlineMs, now));
    final hint = (seconds == null || seconds <= 0) ? defaultWaitSeconds : min(seconds, maxWaitSeconds);
    final storageKeys = keys.map(_storageKey).toList();
    final previousBase = storageKeys.fold(0, (base, key) => max(base, _waits[key]?.baseSeconds ?? 0));
    final base = max(hint, min(_maxBaseSeconds, previousBase * 2));
    final jitter = min(maxWaitSeconds - base, max(1, base ~/ 4));
    final deadline = now + (base + _random.nextInt(jitter + 1)) * 1000;
    for (final key in storageKeys) {
      _waits[key] = (deadlineMs: deadline, baseSeconds: base);
    }
    await _save();
  }

  Future<void> clear(Set<String> keys) async {
    _loadOwner();
    if (_waits.isEmpty) return;
    var changed = false;
    for (final key in keys) {
      if (_waits.remove(_storageKey(key)) != null) changed = true;
    }
    if (changed) await _save();
  }

  bool _validDeadline(int deadline, int now) =>
      deadline >= now - _streakRetention.inMilliseconds && deadline <= now + maxWaitSeconds * 1000;

  void _loadOwner() {
    final prefs = _prefs;
    if (prefs == null) return;
    final owner = prefs.uid;
    if (_owner == owner) return;
    _owner = owner;
    _waits.clear();
    if (owner.isEmpty) return;
    final raw = prefs.getString(_prefKey);
    if (raw.isEmpty) return;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map || decoded['owner'] != owner) return;
      final waits = decoded['waits'];
      if (waits is! Map<String, dynamic>) return;
      final now = _now().millisecondsSinceEpoch;
      for (final entry in waits.entries) {
        final value = entry.value;
        if (value is List && value.length == 2 && value[0] is int && value[1] is int) {
          final deadline = value[0] as int;
          final base = value[1] as int;
          if (base > 0 && base <= maxWaitSeconds && _validDeadline(deadline, now)) {
            _waits[entry.key] = (deadlineMs: deadline, baseSeconds: base);
          }
        }
      }
    } on FormatException {
      // Corrupt pacing metadata expires independently of the audio ledger.
    }
  }

  Future<void> _save() async {
    final prefs = _prefs;
    final owner = _owner;
    if (prefs == null || owner == null || owner.isEmpty) return;
    try {
      await prefs.saveString(
        _prefKey,
        jsonEncode({
          'owner': owner,
          'waits': {
            for (final entry in _waits.entries) entry.key: [entry.value.deadlineMs, entry.value.baseSeconds]
          },
        }),
      );
    } catch (_) {
      // Keep pacing in memory when storage is unavailable.
    }
  }
}
