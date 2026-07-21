import 'dart:async';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:omi_device/omi_device.dart';

/// Scanned Omi-capable BLE peripheral.
class OmiBleDevice {
  const OmiBleDevice({
    required this.id,
    required this.name,
    this.rssi = 0,
  });

  final String id;
  final String name;
  final int rssi;
}

typedef AudioPacketHandler = void Function(List<int> packet);

/// High-level Omi BLE surface (scan / connect / audio notify).
abstract class OmiBleClient {
  Future<List<OmiBleDevice>> scan({Duration timeout = const Duration(seconds: 5)});
  Future<void> connect(String deviceId);
  Future<void> listenAudio(AudioPacketHandler onPacket);
  Future<void> listenPayload(AudioPacketHandler onPayload);
  Future<void> disconnect();
}

/// [OmiBleClient] backed by [flutter_blue_plus]. Flutter-only.
class FlutterBluePlusOmiBle implements OmiBleClient {
  BluetoothDevice? _device;
  BluetoothCharacteristic? _audioChar;
  StreamSubscription<List<int>>? _notifySub;

  @override
  Future<List<OmiBleDevice>> scan({Duration timeout = const Duration(seconds: 5)}) async {
    final byId = <String, OmiBleDevice>{};
    final sub = FlutterBluePlus.scanResults.listen((results) {
      for (final r in results) {
        final id = r.device.remoteId.str;
        byId[id] = OmiBleDevice(
          id: id,
          name: r.device.platformName,
          rssi: r.rssi,
        );
      }
    });
    try {
      await FlutterBluePlus.startScan(
        withServices: [Guid(omiServiceUuid)],
        timeout: timeout,
      );
    } finally {
      await sub.cancel();
      if (FlutterBluePlus.isScanningNow) {
        await FlutterBluePlus.stopScan();
      }
    }
    return byId.values.toList();
  }

  @override
  Future<void> connect(String deviceId) async {
    await disconnect();
    final device = BluetoothDevice.fromId(deviceId);
    await device.connect(autoConnect: false);
    final services = await device.discoverServices();
    BluetoothCharacteristic? audio;
    final serviceGuid = Guid(omiServiceUuid);
    final audioGuid = Guid(audioDataUuid);
    for (final service in services) {
      if (service.uuid != serviceGuid) continue;
      for (final c in service.characteristics) {
        if (c.uuid == audioGuid) {
          audio = c;
          break;
        }
      }
      if (audio != null) break;
    }
    if (audio == null) {
      await device.disconnect();
      throw StateError('Omi audio characteristic $audioDataUuid not found');
    }
    _device = device;
    _audioChar = audio;
  }

  @override
  Future<void> listenAudio(AudioPacketHandler onPacket) async {
    final char = _audioChar;
    if (char == null) {
      throw StateError('Not connected — call connect() first');
    }
    await _notifySub?.cancel();
    _notifySub = char.onValueReceived.listen(onPacket);
    final ok = await char.setNotifyValue(true);
    if (!ok) {
      await _notifySub?.cancel();
      _notifySub = null;
      throw StateError('Failed to enable audio notifications');
    }
  }

  @override
  Future<void> listenPayload(AudioPacketHandler onPayload) {
    return listenAudio((packet) {
      final payload = stripPacketHeader(packet);
      if (payload.isNotEmpty) onPayload(payload);
    });
  }

  @override
  Future<void> disconnect() async {
    await _notifySub?.cancel();
    _notifySub = null;
    final char = _audioChar;
    _audioChar = null;
    if (char != null && char.isNotifying) {
      try {
        await char.setNotifyValue(false);
      } catch (_) {}
    }
    final device = _device;
    _device = null;
    if (device != null) {
      try {
        await device.disconnect();
      } catch (_) {}
    }
  }
}
