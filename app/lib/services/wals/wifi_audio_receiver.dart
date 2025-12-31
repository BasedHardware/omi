import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

/// WiFi Audio Receiver - TCP server for receiving audio data from Omi device
class WifiAudioReceiver {
  static const int defaultPort = 12345;
  static const int packetSize = 440;

  static WifiAudioReceiver? _instance;
  static WifiAudioReceiver get instance {
    _instance ??= WifiAudioReceiver._();
    return _instance!;
  }

  WifiAudioReceiver._();

  factory WifiAudioReceiver() {
    return instance;
  }

  ServerSocket? _serverSocket;
  Socket? _clientSocket;
  StreamController<List<int>>? _audioStreamController;
  bool _isRunning = false;

  Stream<List<int>>? get audioStream => _audioStreamController?.stream;
  bool get isRunning => _isRunning;

  /// Get the local IP address for the TCP server
  Future<String?> getLocalIpAddress() async {
    try {
      final interfaces = await NetworkInterface.list(
        type: InternetAddressType.IPv4,
        includeLoopback: false,
        includeLinkLocal: false,
      );

      for (final interface in interfaces) {
        for (final addr in interface.addresses) {
          final ip = addr.address;
          debugPrint('WifiAudioReceiver: Found interface ${interface.name}: $ip');
          if (ip.startsWith('172.20.10.')) {
            debugPrint('WifiAudioReceiver: Using iOS hotspot: $ip');
            return ip;
          }
        }
      }

      for (final interface in interfaces) {
        for (final addr in interface.addresses) {
          final ip = addr.address;
          if ((ip.startsWith('192.168.') || ip.startsWith('172.')) &&
              (interface.name.contains('ap') || interface.name.contains('wlan') || interface.name.contains('bridge'))) {
            debugPrint('WifiAudioReceiver: Using hotspot interface: $ip');
            return ip;
          }
        }
      }

      for (final interface in interfaces) {
        for (final addr in interface.addresses) {
          final ip = addr.address;
          if (ip.startsWith('192.168.') || ip.startsWith('172.') || ip.startsWith('10.')) {
            debugPrint('WifiAudioReceiver: Fallback to: $ip');
            return ip;
          }
        }
      }

      return null;
    } catch (e) {
      debugPrint('WifiAudioReceiver: Error getting IP: $e');
      return null;
    }
  }

  /// Start the TCP server
  Future<bool> start({int port = defaultPort}) async {
    if (_isRunning || _serverSocket != null) {
      debugPrint('WifiAudioReceiver: Already running, stopping first...');
      await stop();
      await Future.delayed(const Duration(milliseconds: 200));
    }

    try {
      _serverSocket = await ServerSocket.bind(
        InternetAddress.anyIPv4,
        port,
        shared: true,
      );
      _audioStreamController = StreamController<List<int>>.broadcast();
      _isRunning = true;

      debugPrint('WifiAudioReceiver: TCP server started on port $port');

      _serverSocket!.listen(
        (Socket client) {
          debugPrint('WifiAudioReceiver: Client connected from ${client.remoteAddress.address}:${client.remotePort}');
          _clientSocket = client;

          client.listen(
            (List<int> data) {
              debugPrint('WifiAudioReceiver: Received ${data.length} bytes');
              _audioStreamController?.add(data);
            },
            onError: (error) {
              debugPrint('WifiAudioReceiver: Client error: $error');
            },
            onDone: () {
              debugPrint('WifiAudioReceiver: Client disconnected');
              _clientSocket = null;
            },
          );
        },
        onError: (error) {
          debugPrint('WifiAudioReceiver: Server error: $error');
        },
        onDone: () {
          debugPrint('WifiAudioReceiver: Server closed');
          _isRunning = false;
        },
      );

      return true;
    } catch (e) {
      debugPrint('WifiAudioReceiver: Failed to start TCP server: $e');
      _isRunning = false;
      _serverSocket = null;
      return false;
    }
  }

  /// Stop the TCP server
  Future<void> stop() async {
    debugPrint('WifiAudioReceiver: Stopping TCP server');

    try {
      await _clientSocket?.close();
    } catch (_) {}
    _clientSocket = null;

    try {
      await _serverSocket?.close();
    } catch (_) {}
    _serverSocket = null;

    try {
      await _audioStreamController?.close();
    } catch (_) {}
    _audioStreamController = null;

    _isRunning = false;
  }

  Future<void> dispose() async => await stop();
}
