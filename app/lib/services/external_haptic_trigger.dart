typedef ExternalHapticPlayer = Future<bool> Function(String deviceId, int level);
typedef ExternalHapticElapsed = Duration Function();

enum ExternalHapticTriggerResult {
  notHandled,
  noPairedDevice,
  rateLimited,
  played,
  unavailable,
}

class ExternalHapticTrigger {
  const ExternalHapticTrigger({required this.level});

  static const Set<String> _supportedSchemes = {'omi', 'omi-dev', 'omi-beta'};
  static const Set<String> _supportedLevels = {'1', '2', '3'};

  final int level;

  static ExternalHapticTrigger? tryParse(Uri uri) {
    if (!_supportedSchemes.contains(uri.scheme.toLowerCase())) return null;
    if (uri.host.toLowerCase() != 'device') return null;
    if (uri.pathSegments.length != 1 || uri.pathSegments.single != 'haptic') return null;

    final levels = uri.queryParametersAll['level'];
    if (levels == null || levels.length != 1 || !_supportedLevels.contains(levels.single)) return null;

    return ExternalHapticTrigger(level: int.parse(levels.single));
  }
}

class ExternalHapticRateLimiter {
  ExternalHapticRateLimiter({
    Duration cooldown = const Duration(seconds: 2),
    ExternalHapticElapsed? elapsed,
  })  : cooldown = cooldown,
        _elapsed = elapsed ?? _monotonicElapsed() {
    if (cooldown.inMicroseconds <= 0) {
      throw ArgumentError.value(cooldown, 'cooldown', 'must be greater than zero');
    }
  }

  final Duration cooldown;
  final ExternalHapticElapsed _elapsed;
  final Map<String, Duration> _lastAcceptedAt = <String, Duration>{};

  static ExternalHapticElapsed _monotonicElapsed() {
    final stopwatch = Stopwatch()..start();
    return () => stopwatch.elapsed;
  }

  bool tryAcquire(String deviceId) {
    final now = _elapsed();
    final lastAcceptedAt = _lastAcceptedAt[deviceId];
    if (lastAcceptedAt != null && now - lastAcceptedAt < cooldown) return false;

    // Reserve synchronously before any awaited connection or BLE write. This keeps
    // concurrent deep-link deliveries from racing through the same cooldown slot.
    _lastAcceptedAt[deviceId] = now;
    return true;
  }
}

Future<ExternalHapticTriggerResult> runExternalHapticTrigger(
  Uri uri, {
  required String deviceId,
  required ExternalHapticRateLimiter rateLimiter,
  required ExternalHapticPlayer playHaptic,
}) async {
  final trigger = ExternalHapticTrigger.tryParse(uri);
  if (trigger == null) return ExternalHapticTriggerResult.notHandled;
  if (deviceId.isEmpty) return ExternalHapticTriggerResult.noPairedDevice;
  if (!rateLimiter.tryAcquire(deviceId)) return ExternalHapticTriggerResult.rateLimited;

  final played = await playHaptic(deviceId, trigger.level);
  return played ? ExternalHapticTriggerResult.played : ExternalHapticTriggerResult.unavailable;
}
