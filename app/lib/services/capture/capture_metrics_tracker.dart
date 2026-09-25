import 'dart:async';

import 'package:flutter/foundation.dart';

class CaptureMetricsTracker {
  CaptureMetricsTracker({required this.onNotify});

  final VoidCallback onNotify;

  int _bleBytesReceived = 0;
  int _wsSocketBytesSent = 0;
  int _lifetimeBleBytesReceived = 0;
  int _lifetimeWsSocketBytesSent = 0;
  double _bleReceiveRateKbps = 0.0;
  double _wsSendRateKbps = 0.0;
  DateTime? _lastCalculated;
  Timer? _timer;
  int _listenersCount = 0;
  bool _captureActive = false;
  bool _appActive = true;

  double get bleReceiveRateKbps => _bleReceiveRateKbps;
  double get wsSendRateKbps => _wsSendRateKbps;
  int get lifetimeBleBytesReceived => _lifetimeBleBytesReceived;
  int get lifetimeWsSocketBytesSent => _lifetimeWsSocketBytesSent;

  @visibleForTesting
  bool get isSampling => _timer?.isActive ?? false;

  void addMetricsListener() {
    _listenersCount++;
    if (_listenersCount == 1) {
      onNotify();
      _syncTimer();
    }
  }

  void removeMetricsListener() {
    if (_listenersCount > 0) {
      _listenersCount--;
    }
    _syncTimer();
  }

  void addBleBytes(int count) {
    _lifetimeBleBytesReceived += count;
    _bleBytesReceived += count;
  }

  void addSocketBytes(int count) {
    _lifetimeWsSocketBytesSent += count;
    _wsSocketBytesSent += count;
  }

  void start() {
    _captureActive = true;
    _bleBytesReceived = 0;
    _wsSocketBytesSent = 0;
    _bleReceiveRateKbps = 0.0;
    _wsSendRateKbps = 0.0;
    _lastCalculated = null;
    _syncTimer();
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
    _captureActive = false;
    _syncTimer();
    _bleBytesReceived = 0;
    _wsSocketBytesSent = 0;
    _bleReceiveRateKbps = 0.0;
    _wsSendRateKbps = 0.0;
    _lastCalculated = null;
    onNotify();
  }

  /// The 5-second sampler exists only to refresh the on-screen diagnostics UI.
  /// Audio byte accounting remains monotonic while the app is backgrounded.
  void setAppActive(bool active) {
    if (_appActive == active) return;
    _appActive = active;
    _syncTimer();
  }

  void _syncTimer() {
    final shouldSample = _captureActive && _appActive && _listenersCount > 0;
    if (!shouldSample) {
      _timer?.cancel();
      _timer = null;
      _lastCalculated = null;
      return;
    }
    if (_timer?.isActive ?? false) return;
    // Rates are a live UI signal, so exclude bytes accumulated while sampling
    // was paused (backgrounded or with no interested widget).
    _bleBytesReceived = 0;
    _wsSocketBytesSent = 0;
    _lastCalculated = DateTime.now();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => calculate());
  }

  void dispose() {
    _timer?.cancel();
  }
}
