typedef ExternalHapticPlayer = Future<bool> Function(String deviceId, int level);

enum ExternalHapticTriggerResult {
  notHandled,
  noPairedDevice,
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

Future<ExternalHapticTriggerResult> runExternalHapticTrigger(
  Uri uri, {
  required String deviceId,
  required ExternalHapticPlayer playHaptic,
}) async {
  final trigger = ExternalHapticTrigger.tryParse(uri);
  if (trigger == null) return ExternalHapticTriggerResult.notHandled;
  if (deviceId.isEmpty) return ExternalHapticTriggerResult.noPairedDevice;

  final played = await playHaptic(deviceId, trigger.level);
  return played ? ExternalHapticTriggerResult.played : ExternalHapticTriggerResult.unavailable;
}
