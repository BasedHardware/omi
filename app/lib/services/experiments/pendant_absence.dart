// Tracks observed pendant absence for foreground churn prompts.
// Survey and reconnect prompts share one local calendar-day claim.
import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/device.dart';
import 'package:omi/utils/logger.dart';

/// Shared by the pendant-stop question (SCA-4815) and reconnect nudge (SCA-4889).
class PendantAbsence {
  PendantAbsence({DateTime Function()? now}) : _now = now ?? DateTime.now;

  static final instance = PendantAbsence();

  /// Both surfaces check and claim this same install-wide local calendar day.
  static const lastSurfaceDayKey = 'pendant_dropoff_surface_last_day';

  /// Local presentation receipts, keyed by a one-way account digest. These
  /// survive ordinary sign-out and are cleared with install/account deletion.
  /// They provide no cross-device deduplication.
  static const questionReceiptsKey = 'pendant_stop_question_receipts';

  final DateTime Function() _now;
  final _prefs = SharedPreferencesUtil();

  static bool isPendant(BtDevice? device) {
    if (device == null || device.id.isEmpty) return false;
    return device.type == DeviceType.friendPendant ||
        (device.type == DeviceType.omi &&
            DeviceUtils.isOmiCv1(modelNumber: device.modelNumber, deviceName: device.name));
  }

  String _digest(String uid) => sha256.convert(utf8.encode('pendant-absence:$uid')).toString();
  String _lastConnectionKey(String uid) => 'pendant_last_connected_at:${_digest(uid)}';
  String _absenceStartKey(String uid) => 'pendant_absence_started_at:${_digest(uid)}';

  void recordConnection(String uid) {
    if (uid.isEmpty) return;
    _persist(_prefs.saveInt(_lastConnectionKey(uid), _now().millisecondsSinceEpoch));
    _persist(_prefs.remove(_absenceStartKey(uid)));
  }

  /// Call on link loss or when foregrounding without a link to a remembered
  /// pendant. The first observation starts the clock even for existing pairs.
  void observeAbsence(String uid) {
    if (uid.isEmpty) return;
    final key = _absenceStartKey(uid);
    if (_prefs.getInt(key) == 0) {
      _persist(_prefs.saveInt(key, _now().millisecondsSinceEpoch));
    }
  }

  int? eligibleDays(String uid, {required BtDevice paired, required bool connected}) {
    if (uid.isEmpty || connected || !isPendant(paired)) return null;
    final anchor = max(_prefs.getInt(_lastConnectionKey(uid)), _prefs.getInt(_absenceStartKey(uid)));
    if (anchor == 0) return null;
    final days = _now().difference(DateTime.fromMillisecondsSinceEpoch(anchor)).inDays;
    return days >= 3 ? days : null;
  }

  String get _today {
    final local = _now().toLocal();
    return '${local.year.toString().padLeft(4, '0')}-'
        '${local.month.toString().padLeft(2, '0')}-${local.day.toString().padLeft(2, '0')}';
  }

  bool get surfaceShownToday => _prefs.getString(lastSurfaceDayKey) == _today;

  /// The preferences cache updates synchronously, so both foreground surfaces
  /// can check and claim on the UI isolate before yielding or presenting.
  bool claimSurfaceToday() {
    final day = _today;
    if (_prefs.getString(lastSurfaceDayKey) == day) return false;
    _persist(_prefs.saveString(lastSurfaceDayKey, day));
    return true;
  }

  bool questionShown(String uid) => _prefs.getStringList(questionReceiptsKey).contains(_digest(uid));

  bool claimQuestion(String uid) {
    if (uid.isEmpty || questionShown(uid) || !claimSurfaceToday()) return false;
    _persist(_prefs.saveStringList(questionReceiptsKey, [..._prefs.getStringList(questionReceiptsKey), _digest(uid)]));
    return true;
  }

  void _persist(Future<bool> write) {
    unawaited(write.then<void>((ok) {
      if (!ok) Logger.debug('Could not persist pendant absence state');
    }, onError: (Object error) {
      Logger.debug('Could not persist pendant absence state: ${error.runtimeType}');
    }));
  }
}
