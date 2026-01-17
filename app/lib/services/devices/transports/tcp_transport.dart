import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'device_transport.dart';

class TcpTransport extends DeviceTransport {
  final String _deviceId;
  final int port;
  final Duration connectionTimeout;

  final StreamController<DeviceTransportState> _connectionStateController;
  StreamController<List<int>>? _dataStreamController;

  ServerSocket? _serverSocket;
  Socket? _clientSocket;
  StreamSubscription? _clientSubscription;
  DeviceTransportState _state = DeviceTransportState.disconnected;

  TcpTransport(
    this._deviceId, {
    required this.port,
    this.connectionTimeout = const Duration(seconds: 30),
  }) : _connectionStateController = StreamController<DeviceTransportState>.broadcast();

  @override
  String get deviceId => _deviceId;

  @override
  Stream<DeviceTransportState> get connectionStateStream => _connectionStateController.stream;

  /// Stream of incoming data from the connected device.
  Stream<List<int>> get dataStream => _dataStreamController?.stream ?? const Stream.empty();

  /// Write data to the connected device.
  Future<void> write(List<int> data) async {
    if (_clientSocket == null || _state != DeviceTransportState.connected) {
      throw StateError('TcpTransport: Cannot write - no client connected');
    }

    try {
      _clientSocket!.add(data);
      await _clientSocket!.flush();
    } catch (e) {
      debugPrint('TcpTransport: Error writing data: $e');
      rethrow;
    }
  }

  void _updateState(DeviceTransportState newState) {
    if (_state != newState) {
      _state = newState;
      _connectionStateController.add(_state);
    }
  }

  @override
  Future<void> connect({bool autoConnect = false}) async {
    if (_state == DeviceTransportState.connected) {
      return;
    }

    _dataStreamController = StreamController<List<int>>.broadcast();
    _updateState(DeviceTransportState.connecting);

    try {
      _serverSocket = await ServerSocket.bind(InternetAddress.anyIPv4, port);

      final clientFuture = _serverSocket!.first.timeout(
        connectionTimeout,
        onTimeout: () {
          throw TimeoutException('No device connected within ${connectionTimeout.inSeconds} seconds');
        },
      );

      _clientSocket = await clientFuture;
      _updateState(DeviceTransportState.connected);

      // Listen for incoming data from the device
      _clientSubscription = _clientSocket!.listen(
        (List<int> data) {
          _dataStreamController?.add(data);
        },
        onError: (error) {
          debugPrint('TcpTransport: Socket error: $error');
          _dataStreamController?.addError(error);
          disconnect();
        },
        onDone: () {
          disconnect();
        },
        cancelOnError: false,
      );
    } on SocketException catch (e) {
      debugPrint('TcpTransport: Socket exception starting server on port $port: $e');
      _updateState(DeviceTransportState.disconnected);
      await _cleanup();
      rethrow;
    } on TimeoutException catch (e) {
      debugPrint('TcpTransport: $e');
      _updateState(DeviceTransportState.disconnected);
      await _cleanup();
      rethrow;
    } catch (e) {
      debugPrint('TcpTransport: Failed to start server on port $port: $e');
      _updateState(DeviceTransportState.disconnected);
      await _cleanup();
      rethrow;
    }
  }

  Future<void> _cleanup() async {
    await _clientSubscription?.cancel();
    _clientSubscription = null;

    try {
      await _clientSocket?.close();
    } catch (e) {
      debugPrint('TcpTransport: Error closing client socket: $e');
    }
    _clientSocket = null;

    try {
      await _serverSocket?.close();
    } catch (e) {
      debugPrint('TcpTransport: Error closing server socket: $e');
    }
    _serverSocket = null;
  }

  @override
  Future<void> disconnect() async {
    if (_state == DeviceTransportState.disconnected) {
      return;
    }

    _updateState(DeviceTransportState.disconnecting);

    await _cleanup();

    try {
      await _dataStreamController?.close();
    } catch (e) {
      debugPrint('TcpTransport: Error closing data stream: $e');
    }
    _dataStreamController = null;

    _updateState(DeviceTransportState.disconnected);
  }

  @override
  Future<bool> isConnected() async {
    return _clientSocket != null && _state == DeviceTransportState.connected;
  }

  @override
  Future<bool> ping() async {
    if (_clientSocket == null || _state != DeviceTransportState.connected) {
      return false;
    }

    try {
      _clientSocket!.remoteAddress;
      return true;
    } catch (e) {
      debugPrint('TcpTransport: Ping failed: $e');
      return false;
    }
  }

  @override
  Stream<List<int>> getCharacteristicStream(String serviceUuid, String characteristicUuid) {
    // TCP doesn't use characteristics - use dataStream instead
    return const Stream.empty();
  }

  @override
  Future<List<int>> readCharacteristic(String serviceUuid, String characteristicUuid) async {
    // TCP doesn't use characteristics - use dataStream instead
    return [];
  }

  @override
  Future<void> writeCharacteristic(String serviceUuid, String characteristicUuid, List<int> data) async {
    // TCP doesn't use characteristics - use write() instead
    await write(data);
  }

  @override
  Future<void> dispose() async {
    await disconnect();
    try {
      await _connectionStateController.close();
    } catch (e) {
      debugPrint('TcpTransport: Error closing state controller: $e');
    }
  }
}
