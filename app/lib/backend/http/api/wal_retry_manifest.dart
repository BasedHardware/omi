import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;

import 'sync_upload_refusal.dart';

/// A disposable hint. The existing WAL ledger and recording cooldown survive
/// process death; starting without a hint goes directly to the ordinary upload.
class WalRetryManifests {
  WalRetryManifests(this._now);

  final DateTime Function() _now;
  final _handles = <String, String>{};

  static String key(String uid, String device, String target, List<Map<String, String>> claims) =>
      sha256.convert(utf8.encode(jsonEncode([uid, device, target, claims]))).toString();

  bool _live(String handle) {
    if (!RegExp(r'^[0-9]{10}\.[0-9a-f]{64}$').hasMatch(handle)) return false;
    final remaining = int.parse(handle.substring(0, 10)) - _now().millisecondsSinceEpoch ~/ 1000;
    return remaining > 0 && remaining <= 120;
  }

  void remember(String key, http.Response upload) {
    final handle = upload.headers['x-omi-wal-retry'];
    if (upload.statusCode != 503 ||
        syncUploadServerWaitReasonCode(upload) != recordCapturePending ||
        handle == null ||
        !_live(handle)) return;
    if (_handles.length >= 64) _handles.remove(_handles.keys.first);
    _handles[key] = handle;
  }

  String? take(String key) {
    final handle = _handles.remove(key);
    return handle != null && _live(handle) ? handle : null;
  }

  /// A probe can only defer. Every other response goes through ordinary upload admission.
  bool confirmsWait(String handle, http.Response? response) =>
      _live(handle) &&
      response?.statusCode == 503 &&
      syncUploadServerWaitReasonCode(response!) == recordCapturePending &&
      syncUploadServerWaitSeconds(response) != null;
}
