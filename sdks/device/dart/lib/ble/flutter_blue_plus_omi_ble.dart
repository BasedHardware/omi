import 'dart:async';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '../omi_device.dart';
import '../uuids.dart';
import 'omi_ble.dart';

/// Portable Omi BLE client using flutter_blue_plus.
///
/// UUID map and audio/codec/battery flows mirror the main app:
/// - `app/lib/services/devices/models.dart`
/// - `app/lib/services/devices/connectors/omi_connection.dart`
///
/// The production app uses native Pigeon BLE for lifecycle; this SDK package
/// uses FBP so third-party Flutter apps can talk to Omi without the full app.
class FlutterBluePlusOmiBle implements OmiBleClient {
  BluetoothDevice? _device;
  List<BluetoothService> _services = const [];
  StreamSubscription<List<int>>? _audioSub;
  final StreamController<List<int>> _audioController = StreamController<List<int>>.broadcast();

  static String _norm(String uuid) => uuid.toLowerCase();

  BluetoothCharacteristic? _findChar(String serviceUuid, String charUuid) {
    final sTarget = _norm(serviceUuid);
    final cTarget = _norm(charUuid);
    for (final s in _services) {
      if (_norm(s.uuid.str128) != sTarget && _norm(s.uuid.str) != sTarget) continue;
      for (final c in s.characteristics) {
        if (_norm(c.uuid.str128) == cTarget || _norm(c.uuid.str) == cTarget) {
          return c;
        }
      }
    }
    // Fallback: search all services by characteristic UUID only.
    for (final s in _services) {
      for (final c in s.characteristics) {
        if (_norm(c.uuid.str128) == cTarget || _norm(c.uuid.str) == cTarget) {
          return c;
        }
      }
    }
    return null;
  }

  @override
  Future<List<BleDevice>> scan({Duration timeout = const Duration(seconds: 5)}) async {
    if (await FlutterBluePlus.isSupported == false) {
      throw UnsupportedError('Bluetooth not supported on this platform');
    }
    // App discoverer filters devices advertising Omi service UUID.
    final withServices = [Guid(omiServiceUuid)];
    final seen = <String, BleDevice>{};

    final sub = FlutterBluePlus.scanResults.listen((results) {
      for (final r in results) {
        final id = r.device.remoteId.str;
        final name = r.advertisementData.advName.isNotEmpty
            ? r.advertisementData.advName
            : r.device.platformName;
        // Keep strongest RSSI
        final prev = seen[id];
        if (prev == null || r.rssi > prev.rssi) {
          seen[id] = BleDevice(id: id, name: name, rssi: r.rssi);
        }
      }
    });

    try {
      await FlutterBluePlus.startScan(
        timeout: timeout,
        withServices: withServices,
        androidUsesFineLocation: true,
      );
      await Future<void>.delayed(timeout);
    } finally {
      await FlutterBluePlus.stopScan();
      await sub.cancel();
    }

    final list = seen.values.toList()..sort((a, b) => b.rssi.compareTo(a.rssi));
    return list;
  }

  @override
  Future<void> connect(String deviceId) async {
    await disconnect();
    final device = BluetoothDevice.fromId(deviceId);
    await device.connect(autoConnect: false, mtu: 512);
    // MTU 512 requested via connect(mtu: 512) for audio throughput (matches RN).
    _services = await device.discoverServices();
    _device = device;
  }

  @override
  Future<void> disconnect() async {
    await _audioSub?.cancel();
    _audioSub = null;
    final d = _device;
    _device = null;
    _services = const [];
    if (d != null) {
      try {
        await d.disconnect();
      } catch (_) {}
    }
  }

  @override
  Future<bool> isConnected() async {
    final d = _device;
    if (d == null) return false;
    return d.isConnected;
  }

  @override
  Stream<List<int>> audioPackets() {
    final device = _device;
    if (device == null) {
      return Stream.error(StateError('not connected'));
    }
    final char = _findChar(omiServiceUuid, audioDataStreamCharacteristicUuid);
    if (char == null) {
      return Stream.error(StateError('audio characteristic not found'));
    }

    // Lazily subscribe once.
    if (_audioSub == null) {
      scheduleMicrotask(() async {
        try {
          await char.setNotifyValue(true);
          _audioSub = char.onValueReceived.listen((value) {
            if (!_audioController.isClosed) {
              _audioController.add(List<int>.from(value));
            }
          });
          device.cancelWhenDisconnected(_audioSub!);
        } catch (e, st) {
          if (!_audioController.isClosed) {
            _audioController.addError(e, st);
          }
        }
      });
    }
    return _audioController.stream;
  }

  @override
  Stream<List<int>> audioPayloads() =>
      audioPackets().map(stripPacketHeader).where((p) => p.isNotEmpty);

  @override
  Future<int> readCodec() async {
    final char = _findChar(omiServiceUuid, audioCodecCharacteristicUuid);
    if (char == null) return -1;
    final data = await char.read();
    if (data.isEmpty) return -1;
    // App defaults unknown empty to 1 (PCM8); expose raw first byte.
    return data[0];
  }

  @override
  Future<int> readBatteryLevel() async {
    final char = _findChar(batteryServiceUuid, batteryLevelCharacteristicUuid);
    if (char == null) return -1;
    final data = await char.read();
    if (data.isEmpty) return -1;
    return data[0];
  }
}
