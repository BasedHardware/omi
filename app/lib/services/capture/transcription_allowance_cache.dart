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

  static TranscriptionAllowanceSnapshot? _memory;

  static TranscriptionAllowanceSnapshot? get current {
    if (_memory != null) return _memory;
    return _readPersisted();
  }

  static void replace(TranscriptionAllowanceSnapshot? value) {
    _memory = value;
    if (value == null) {
      SharedPreferencesUtil().saveString(prefsKey, '');
      return;
    }
    SharedPreferencesUtil().saveString(prefsKey, jsonEncode(value.toJson()));
  }

  static void clear() {
    _memory = null;
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
