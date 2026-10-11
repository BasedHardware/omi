import 'dart:io';

import 'package:flutter/services.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/utils/logger.dart';

/// Bridges an opportunistic iOS task to the existing, configured recovery owner.
/// Android's existing foreground-task repeat callback sends the same wake.
/// This bridge has no capture/device-start dependency.
class PeriodicRecordingSync {
  PeriodicRecordingSync({required this.coordinator, required this.cancel, bool? isIOS})
      : _isIOS = isIOS ?? Platform.isIOS;

  static const channel = MethodChannel('com.omi/periodic_recording_sync');
  final RecordingTransferCoordinator coordinator;
  final void Function() cancel;
  final bool _isIOS;
  bool _disposed = false;

  Future<void> start() async {
    if (!_isIOS || _disposed) return;
    channel.setMethodCallHandler((call) async {
      if (_disposed) return false;
      switch (call.method) {
        case 'wake':
          await coordinator.wake(WakeTrigger.periodic);
          await coordinator.waitUntilIdle();
          return !_disposed;
        case 'expire':
          coordinator.cancelPeriodicWake();
          cancel();
          return null;
        default:
          throw MissingPluginException();
      }
    });
    try {
      await channel.invokeMethod<void>('schedule');
    } catch (error) {
      Logger.debug('Periodic recording sync scheduling unavailable: $error');
    }
  }

  void dispose() {
    _disposed = true;
    if (_isIOS) channel.setMethodCallHandler(null);
  }
}
