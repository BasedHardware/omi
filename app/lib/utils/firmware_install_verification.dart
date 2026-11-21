import 'dart:async';

/// Only fresh DIS reads from the reconnect path belong in this stream. Cached
/// pairing metadata and DFU transport success are not installation evidence.
typedef FirmwareRevisionObservation = ({String deviceId, String version});

enum FirmwareInstallOutcome { installed, notInstalled, noReconnect }

class FirmwareInstallResult {
  const FirmwareInstallResult(this.outcome, [this.observedVersion]);

  final FirmwareInstallOutcome outcome;
  final String? observedVersion;
}

bool isKnownFirmwareVersion(String? version) =>
    version != null && version.trim().isNotEmpty && version.trim().toLowerCase() != 'unknown';

Future<FirmwareInstallResult> verifyFirmwareInstallation({
  required Stream<FirmwareRevisionObservation> observations,
  required String deviceId,
  required String fromVersion,
  String? targetVersion,
  Duration timeout = const Duration(minutes: 3),
}) async {
  final result = Completer<FirmwareInstallResult>();
  final subscription = observations.listen((observation) {
    if (result.isCompleted || observation.deviceId != deviceId || !isKnownFirmwareVersion(observation.version)) return;
    final observed = observation.version.trim();
    final knownBefore = isKnownFirmwareVersion(fromVersion);
    final matchesTarget = isKnownFirmwareVersion(targetVersion) && observed == targetVersion!.trim();
    result.complete(FirmwareInstallResult(
      // A known unchanged revision is never proof of installation, including
      // a rollback whose target was already running before this attempt.
      (knownBefore ? observed != fromVersion.trim() : matchesTarget)
          ? FirmwareInstallOutcome.installed
          : FirmwareInstallOutcome.notInstalled,
      observed,
    ));
  });
  final timer = Timer(timeout, () {
    if (!result.isCompleted) result.complete(const FirmwareInstallResult(FirmwareInstallOutcome.noReconnect));
  });
  try {
    return await result.future;
  } finally {
    timer.cancel();
    // Detach immediately; asynchronous stream cleanup must not extend the deadline.
    unawaited(subscription.cancel());
  }
}
