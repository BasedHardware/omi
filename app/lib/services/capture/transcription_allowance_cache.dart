import 'dart:convert';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/utils/logger.dart';

/// Last-known-good S16 snapshot for the STT resolver.
///
/// Memory first, then the persisted copy so a failed refresh does not drop a
/// known basic user onto a billed socket.
class TranscriptionAllowanceCache {
  static const prefsKey = 'transcriptionAllowanceLastKnown';
  static const savedAtPrefsKey = 'transcriptionAllowanceLastKnownAtMs';

  static TranscriptionAllowanceSnapshot? _memory;

  /// When the last snapshot was stored, or null for a snapshot saved before this was tracked.
  static DateTime? get savedAt {
    final ms = SharedPreferencesUtil().getInt(savedAtPrefsKey);
    return ms <= 0 ? null : DateTime.fromMillisecondsSinceEpoch(ms);
  }

  /// [current] when it was stored within [maxAge] of [now]; null otherwise.
  static TranscriptionAllowanceSnapshot? currentWithin(Duration maxAge, {DateTime? now}) {
    final snapshot = current;
    final at = savedAt;
    if (snapshot == null || at == null) return null;
    return (now ?? DateTime.now()).difference(at) <= maxAge ? snapshot : null;
  }

  static TranscriptionAllowanceSnapshot? get current {
    if (_memory != null) return _memory;
    return _readPersisted();
  }

  static void replace(TranscriptionAllowanceSnapshot? value, {DateTime? now}) {
    _memory = value;
    SharedPreferencesUtil()
        .saveInt(savedAtPrefsKey, value == null ? 0 : (now ?? DateTime.now()).millisecondsSinceEpoch);
    if (value == null) {
      SharedPreferencesUtil().saveString(prefsKey, '');
      return;
    }
    SharedPreferencesUtil().saveString(prefsKey, jsonEncode(value.toJson()));
  }

  static void clear() {
    _memory = null;
    SharedPreferencesUtil().saveInt(savedAtPrefsKey, 0);
    SharedPreferencesUtil().saveString(prefsKey, '');
  }

  static TranscriptionAllowanceSnapshot? _readPersisted() {
    final raw = SharedPreferencesUtil().getString(prefsKey);
    if (raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) return null;
      return TranscriptionAllowanceSnapshot.fromJson(decoded);
    } catch (e) {
      Logger.debug('[SttMode] failed to read persisted transcription allowance: $e');
      return null;
    }
  }
}
