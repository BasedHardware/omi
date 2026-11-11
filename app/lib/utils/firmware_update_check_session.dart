import 'package:flutter/foundation.dart';

@immutable
class FirmwareUpdateCheckSession {
  const FirmwareUpdateCheckSession._({required this.deviceId, required this.generation});

  final String deviceId;
  final int generation;
}

/// Identifies the exact device connection that owns an asynchronous firmware
/// check. Reconnecting the same physical device still creates a new session.
class FirmwareUpdateCheckSessionGuard {
  int _generation = 0;
  String? _deviceId;

  void start(String deviceId) {
    _generation++;
    _deviceId = deviceId;
  }

  void invalidate() {
    _generation++;
    _deviceId = null;
  }

  FirmwareUpdateCheckSession? capture() {
    final deviceId = _deviceId;
    if (deviceId == null) return null;
    return FirmwareUpdateCheckSession._(deviceId: deviceId, generation: _generation);
  }

  bool isCurrent(FirmwareUpdateCheckSession session) {
    return session.generation == _generation && session.deviceId == _deviceId;
  }
}
