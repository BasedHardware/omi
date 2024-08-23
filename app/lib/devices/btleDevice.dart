import 'dart:async';
import 'package:collection/collection.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:friend_private/utils/ble/errors.dart';
import '../utils/ble/BtServiceDef.dart';
import 'device.dart';

abstract class BtleDevice extends Device {
  BtleDevice() : super();
  BluetoothDevice? device;

  int? rssi;
  StreamSubscription<BluetoothConnectionState>?
      _connectionStateStreamSubscription;
  BluetoothConnectionState _connectionState =
      BluetoothConnectionState.disconnected;

  void _initConnectionStateListener(
      Stream<BluetoothConnectionState> connectionStateStream) async {
    if (_connectionStateStreamSubscription != null) {
      _connectionStateStreamSubscription!.cancel();
    }
    _connectionStateStreamSubscription = connectionStateStream.listen((state) {
      if (state == BluetoothConnectionState.connected && _connectionState == BluetoothConnectionState.disconnected) {
        print("Connected to device: $name");
        init();
      } else if (state == BluetoothConnectionState.disconnected && _connectionState == BluetoothConnectionState.connected) {
        print("Disconnected from device: $name");
      }
      _connectionState = state;
    });
  }

  BluetoothConnectionState get connectionState {
    if (_connectionStateStreamSubscription == null) {
      _initConnectionStateListener(connectionStateStream);
    }
    return _connectionState;
  }

  Stream<BluetoothConnectionState> get connectionStateStream {
    device ??= BluetoothDevice.fromId(id);
    return device!.connectionState;
  }

  @override
  bool get isConnected => connectionState == BluetoothConnectionState.connected;

  @override
  Future<Device> connectDevice({bool autoConnect = true}) async {
    if (isConnected) {
      return this;
    }
    device ??= BluetoothDevice.fromId(id);
    try {
      // TODO: for android seems like the reconnect or resetState is not working
      if (!autoConnect) {
        await device!.connect(autoConnect: false);
        return this;
      }
      name = device!.platformName;
      // Step 1: Connect with autoConnect
      await device!.connect(autoConnect: true, mtu: null);
      // Step 2: Listen to the connection state to ensure the device is connected
      _initConnectionStateListener(device!.connectionState);
      await device!.connectionState
          .where((state) => state == BluetoothConnectionState.connected)
          .first;

      rssi = await device!.readRssi();
    } catch (e) {
      print('bleConnectDevice failed: $e');
    }
    return this;
  }

  @override
  Future disconnectDevice() async {
    device ??= BluetoothDevice.fromId(id);
    try {
      await device!.disconnect(queue: false);
    } catch (e) {
      print('bleDisconnectDevice failed: $e');
    }
  }

  Future<BluetoothCharacteristic?> ensureCharacteristicFilled(
      BluetoothCharacteristic? characteristic,
      BtCharacteristicDef characteristicDef) async {
    if (characteristic == null) {
      final service = await getService(characteristicDef.service);
      if (service != null) {
        characteristic = await getCharacteristic(characteristicDef);
      } else {
        logServiceNotFoundError(characteristicDef.service.name, id);
      }
      if (characteristic == null) {
        logCharacteristicNotFoundError(characteristicDef.name, id);
      }
    }
    return characteristic;
  }

  Future<BluetoothService?> getService(BtServiceDef serviceDef) async {
    device ??= BluetoothDevice.fromId(id);
    final allServices = await device!.discoverServices();
    return allServices.firstWhereOrNull((s) => serviceDef.matchesService(s));
  }

  Future<BluetoothCharacteristic?> getCharacteristic(
      BtCharacteristicDef characteristicDef) async {
    final service = await getService(characteristicDef.service);
    if (service == null) {
      return null;
    }
    return service.characteristics
        .firstWhereOrNull((c) => characteristicDef.matchesCharacteristic(c));
  }

  Future<String?> readCharacteristic(
      BtCharacteristicDef characteristicDef) async {
    try {
      var characteristic = await getCharacteristic(characteristicDef);
      if (characteristic == null) {
        return null;
      }
      var value = await characteristic.read();
      return String.fromCharCodes(value);
    } catch (e) {
      print('Error reading characteristic: $e');
      return null;
    }
  }
}
