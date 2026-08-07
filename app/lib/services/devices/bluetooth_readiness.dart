import 'dart:async';
import 'dart:io';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';

enum BluetoothAdapterState { on, off, unauthorized, unsupported, resetting, unknown }

enum BluetoothUse { discovery, connection }

/// A user-actionable adapter problem. Permissions and radio power are distinct:
/// a granted Bluetooth permission does not mean the adapter is switched on.
class BluetoothGuidance {
  final int id;
  final BluetoothAdapterState state;
  final BluetoothUse use;

  const BluetoothGuidance({required this.id, required this.state, required this.use});
}

/// Thrown after guidance has been published so callers cannot mistake a blocked
/// connection attempt for a successfully created transport.
class BluetoothAdapterUnavailableException implements Exception {
  final BluetoothAdapterState state;

  const BluetoothAdapterUnavailableException(this.state);

  @override
  String toString() => 'Bluetooth adapter is unavailable: $state';
}

/// Shared adapter readiness boundary for BLE discovery and connection attempts.
///
/// Native callbacks are treated as updates, while every user-visible operation
/// queries the authoritative native state immediately before it starts. This
/// avoids relying on a startup callback that can arrive before Dart is ready.
class BluetoothReadiness extends ChangeNotifier {
  BluetoothReadiness({
    Future<String> Function()? readState,
    Future<bool> Function()? requestEnable,
    Future<BluetoothAdapterState?> Function(BluetoothUse use)? permissionState,
    bool observeBridge = true,
  })  : _readState = readState ?? (() => BleHostApi().getBluetoothState()),
        _requestEnable = requestEnable ?? (() => BleHostApi().enableBluetooth()),
        _permissionState = permissionState {
    if (observeBridge) {
      _removeBridgeListener = BleBridge.instance.addBluetoothStateListener(_onNativeStateChanged);
    }
  }

  static final BluetoothReadiness instance = BluetoothReadiness();

  final Future<String> Function() _readState;
  final Future<bool> Function() _requestEnable;
  final Future<BluetoothAdapterState?> Function(BluetoothUse use)? _permissionState;
  VoidCallback? _removeBridgeListener;

  BluetoothAdapterState _state = BluetoothAdapterState.unknown;
  BluetoothGuidance? _guidance;
  BluetoothAdapterState? _dismissedBlockedState;
  int _nextGuidanceId = 0;

  BluetoothAdapterState get state => _state;
  BluetoothGuidance? get guidance => _guidance;

  static BluetoothAdapterState parse(String value) => switch (value) {
        'on' => BluetoothAdapterState.on,
        'off' => BluetoothAdapterState.off,
        'unauthorized' => BluetoothAdapterState.unauthorized,
        'unsupported' => BluetoothAdapterState.unsupported,
        'resetting' => BluetoothAdapterState.resetting,
        _ => BluetoothAdapterState.unknown,
      };

  /// Returns false and publishes one deduplicated guidance event when BLE is
  /// unavailable. Call this directly before beginning a BLE operation.
  Future<bool> ensureReady(BluetoothUse use) async {
    final permissionState = await (_permissionState?.call(use) ?? _currentPermissionState(use));
    if (permissionState != null) {
      _applyState(permissionState, use: use);
      return false;
    }
    _applyState(parse(await _readState()), use: use);
    return _state == BluetoothAdapterState.on;
  }

  Future<BluetoothAdapterState?> _currentPermissionState(BluetoothUse use) async {
    if (Platform.isIOS) {
      return await Permission.bluetooth.isGranted ? null : BluetoothAdapterState.unauthorized;
    }
    if (!Platform.isAndroid) return null;

    final sdk = (await DeviceInfoPlugin().androidInfo).version.sdkInt;
    if (sdk < 31) return null;
    final connectGranted = await Permission.bluetoothConnect.isGranted;
    final scanGranted = use == BluetoothUse.discovery ? await Permission.bluetoothScan.isGranted : true;
    return connectGranted && scanGranted ? null : BluetoothAdapterState.unauthorized;
  }

  /// Android opens the platform enable prompt. iOS reports false; its dialog
  /// explains that the user must switch Bluetooth on outside the app.
  Future<bool> requestEnable(BluetoothUse use) async {
    try {
      await _requestEnable();
    } finally {
      final next = parse(await _readState());
      if (next == BluetoothAdapterState.on) {
        _applyState(next);
      } else {
        // The system prompt was cancelled or declined. Suppress the same
        // guidance until the adapter changes state so it cannot immediately
        // reopen after the user dismisses the platform prompt.
        _dismissedBlockedState = next;
        _guidance = null;
        _applyState(next);
        notifyListeners();
      }
    }
    return _state == BluetoothAdapterState.on;
  }

  void dismissGuidance(int id) {
    if (_guidance?.id != id) return;
    _dismissedBlockedState = _guidance!.state;
    _guidance = null;
    notifyListeners();
  }

  @visibleForTesting
  void onNativeStateChangedForTesting(String value) => _onNativeStateChanged(value);

  void _onNativeStateChanged(String value) {
    _applyState(parse(value));
  }

  void _applyState(BluetoothAdapterState next, {BluetoothUse? use}) {
    final previous = _state;
    _state = next;
    if (next == BluetoothAdapterState.on) {
      _dismissedBlockedState = null;
      if (_guidance != null || previous != next) {
        _guidance = null;
        notifyListeners();
      }
      return;
    }

    if (use != null && _guidance == null && _dismissedBlockedState != next) {
      _guidance = BluetoothGuidance(id: ++_nextGuidanceId, state: next, use: use);
      notifyListeners();
      return;
    }
    if (previous != next) notifyListeners();
  }

  @override
  void dispose() {
    _removeBridgeListener?.call();
    _removeBridgeListener = null;
    super.dispose();
  }
}
