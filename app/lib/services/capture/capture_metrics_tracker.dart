import 'dart:async';

import 'package:flutter/foundation.dart';

class CaptureMetricsTracker {
  CaptureMetricsTracker({required this.onNotify});

  final VoidCallback onNotify;

  int _bleBytesReceived = 0;
  int _wsSocketBytesSent = 0;
  double _bleReceiveRateKbps = 0.0;
  double _wsSendRateKbps = 0.0;
  DateTime? _lastCalculated;
  Timer? _timer;
  int _listenersCount = 0;

  double get bleReceiveRateKbps => _bleReceiveRateKbps;
  double get wsSendRateKbps => _wsSendRateKbps;

  void addMetricsListener() {
    _listenersCount++;
    if (_listenersCount == 1) {
      onNotify();
    }
  }

  void removeMetricsListener() {
    if (_listenersCount > 0) {
      _listenersCount--;
    }
  }

  void addBleBytes(int count) {
    _bleBytesReceived += count;
  }

  void addSocketBytes(int count) {
    _wsSocketBytesSent += count;
  }

  void start() {
    _bleBytesReceived = 0;
    _wsSocketBytesSent = 0;
    _bleReceiveRateKbps = 0.0;
    _wsSendRateKbps = 0.0;
    _lastCalculated = DateTime.now();

    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) {
      calculate();
    });
  }

  void calculate() {
    final now = DateTime.now();
    if (_lastCalculated == null) {
      _lastCalculated = now;
      return;
    }

    final elapsedSeconds = now.difference(_lastCalculated!).inMilliseconds / 1000.0;
    if (elapsedSeconds <= 0) return;

    _bleReceiveRateKbps = (_bleBytesReceived * 8) / (elapsedSeconds * 1000);
    _wsSendRateKbps = (_wsSocketBytesSent * 8) / (elapsedSeconds * 1000);
    _bleBytesReceived = 0;
    _wsSocketBytesSent = 0;
    _lastCalculated = now;

    if (_listenersCount > 0) {
      onNotify();
    }
  }

  void calculateForTesting() {
    _lastCalculated ??= DateTime.now().subtract(const Duration(seconds: 10));
    calculate();
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    _bleBytesReceived = 0;
    _wsSocketBytesSent = 0;
    _bleReceiveRateKbps = 0.0;
    _wsSendRateKbps = 0.0;
    _lastCalculated = null;
    onNotify();
  }

  void dispose() {
    _timer?.cancel();
  }
}
