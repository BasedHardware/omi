import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/logger.dart';

/// Native owns the BLE link and Dart mirrors it. Any lost device-ready (a
/// launch connect that timed out, a retired transport, a dropped callback)
/// otherwise leaves the UI disconnected over a live link until the app is
/// killed. On foreground, re-adopt a link native already holds: native answers
/// manageDevice for a connected peripheral by replaying device-ready, so this
/// never touches the radio and never starts a physical connect.
class NativeLinkReconciler {
  NativeLinkReconciler(this._provider, {Future<bool> Function(String deviceId)? nativeLinkProbe})
      : _nativeLinkProbe = nativeLinkProbe ?? BleHostApi().isPeripheralConnected;

  final DeviceProvider _provider;
  final Future<bool> Function(String deviceId) _nativeLinkProbe;
  AppLifecycleListener? _lifecycle;
  bool _disposed = false;

  void bindAppLifecycle() {
    if (_disposed) return;
    _lifecycle ??= AppLifecycleListener(onResume: () => unawaited(reconcile()));
  }

  /// The paired device id while the mirror shows it disconnected, else null.
  String? _disconnectedPairedDeviceId() {
    if (_disposed || _provider.isConnected || _provider.isConnecting || _provider.isFirmwareUpdateInProgress) {
      return null;
    }
    final id = SharedPreferencesUtil().btDevice.id;
    return id.isEmpty ? null : id;
  }

  Future<void> reconcile() async {
    final deviceId = _disconnectedPairedDeviceId();
    if (deviceId == null) return;
    final bool linkUp;
    try {
      linkUp = await _nativeLinkProbe(deviceId);
    } catch (_) {
      return;
    }
    // Adopt only the device whose link was probed: pairing or the mirror may
    // have changed while the probe was in flight.
    if (!linkUp || _disconnectedPairedDeviceId() != deviceId) return;
    Logger.debug('NativeLinkReconciler: native holds $deviceId while disconnected; re-adopting');
    final deviceService = ServiceManager.instance().device;
    if (deviceService.connectionFor(deviceId)?.status == DeviceConnectionState.connected) {
      // DeviceService holds the link but the provider never heard. Admission
      // revalidates the persisted pairing when the debounced handler runs, so
      // a pairing that moved on during the queue is not published.
      _provider.readoptServiceLink(deviceId);
      return;
    }
    // Otherwise native replays device-ready into a fresh transport. Its
    // connected event queues an unguarded admission through the generic path;
    // queue the guarded readoption in its place — the debounced action is
    // single-slot, and this runs as the next microtask after the transport's
    // event, well inside its 100 ms window — so a pairing that moved on while
    // the link was forming is never published.
    final connection = await deviceService.ensureConnection(deviceId, force: true);
    if (connection?.status == DeviceConnectionState.connected) {
      _provider.readoptServiceLink(deviceId);
    }
  }

  void dispose() {
    _disposed = true;
    _lifecycle?.dispose();
    _lifecycle = null;
  }
}
