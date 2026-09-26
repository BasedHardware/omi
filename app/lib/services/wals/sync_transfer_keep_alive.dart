import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:omi/utils/logger.dart';

/// Mobile refcount around bounded native recording-transfer execution.
///
/// Acquiring the first ref starts [SyncTransferForegroundService] (dataSync FGS
/// + PARTIAL_WAKE_LOCK) on Android so BLE/cloud WAL drains survive screen-off
/// (#5221). On iOS it owns a finite UIApplication background task. The last
/// release, [releaseAll], or engine teardown stops the native lease.
class SyncTransferKeepAlive {
  SyncTransferKeepAlive({
    bool Function()? isAndroid,
    bool Function()? isIOS,
    Future<void> Function()? start,
    Future<void> Function()? stop,
  })  : _isAndroid = isAndroid ?? _defaultIsAndroid,
        _isIOS = isIOS ?? _defaultIsIOS,
        _start = start,
        _stop = stop;

  static final SyncTransferKeepAlive instance = SyncTransferKeepAlive();

  static const MethodChannel channel = MethodChannel('com.friend.ios/sync_transfer');

  static bool _defaultIsAndroid() => !kIsWeb && Platform.isAndroid;
  static bool _defaultIsIOS() => !kIsWeb && Platform.isIOS;

  final bool Function() _isAndroid;
  final bool Function() _isIOS;
  final Future<void> Function()? _start;
  final Future<void> Function()? _stop;

  int _refs = 0;

  /// Visible to tests and diagnostics.
  int get refCount => _refs;

  bool get isHeld => _refs > 0;

  Future<void> acquire() async {
    _refs++;
    if (_refs != 1) return;
    await _invokeStart();
  }

  Future<void> release() async {
    if (_refs == 0) return;
    _refs--;
    if (_refs != 0) return;
    await _invokeStop();
  }

  /// Drop every ref and stop the native service. Used by cancel and dispose so
  /// the notification cannot outlive the transfer the user just stopped.
  Future<void> releaseAll() async {
    if (_refs == 0) return;
    _refs = 0;
    await _invokeStop();
  }

  Future<void> _invokeStart() async {
    if (!_isAndroid() && !_isIOS()) return;
    try {
      final start = _start;
      if (start != null) {
        await start();
        return;
      }
      await channel.invokeMethod<void>('start');
    } catch (error) {
      Logger.debug('SyncTransferKeepAlive: start failed: $error');
    }
  }

  Future<void> _invokeStop() async {
    if (!_isAndroid() && !_isIOS()) return;
    try {
      final stop = _stop;
      if (stop != null) {
        await stop();
        return;
      }
      await channel.invokeMethod<void>('stop');
    } catch (error) {
      Logger.debug('SyncTransferKeepAlive: stop failed: $error');
    }
  }
}
