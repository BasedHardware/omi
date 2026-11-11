import 'dart:async';

import '../omi_device.dart';
import 'flutter_blue_plus_omi_ble.dart';

class BleDevice {
  BleDevice({required this.id, required this.name, this.rssi = 0});
  final String id;
  final String name;
  final int rssi;
}

/// BLE client interface aligned with multi-lang device SDKs + Omi app surface.
abstract class OmiBleClient {
  Future<List<BleDevice>> scan({Duration timeout = const Duration(seconds: 5)});
  Future<void> connect(String deviceId);
  Future<void> disconnect();
  Future<bool> isConnected();

  /// Raw audio notify packets (includes 3-byte header).
  Stream<List<int>> audioPackets();

  /// Payload after stripPacketHeader (matches Python listen_payload).
  Stream<List<int>> audioPayloads() => audioPackets().map(stripPacketHeader).where((p) => p.isNotEmpty);

  /// First byte of codec characteristic (app: performGetAudioCodec).
  Future<int> readCodec();

  /// Battery level 0-100, or -1.
  Future<int> readBatteryLevel();
}

/// Default factory: flutter_blue_plus backend (same stack apps commonly use).
OmiBleClient createOmiBleClient() => FlutterBluePlusOmiBle();
