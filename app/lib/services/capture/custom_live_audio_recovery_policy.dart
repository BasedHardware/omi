enum CustomLiveAudioRecoveryGate { enabled, pending, disabled }

/// Resolves the release kill switch and its pending-read state in one place.
CustomLiveAudioRecoveryGate resolveCustomLiveAudioRecoveryGate({
  required bool buildEnabled,
  required bool flagReadContextAvailable,
  required bool? cachedKillSwitchEnabled,
  bool unresolvedRetryExhausted = false,
}) {
  if (!buildEnabled || cachedKillSwitchEnabled == true) return CustomLiveAudioRecoveryGate.disabled;
  if (flagReadContextAvailable && cachedKillSwitchEnabled == null && !unresolvedRetryExhausted) {
    return CustomLiveAudioRecoveryGate.pending;
  }
  return CustomLiveAudioRecoveryGate.enabled;
}

/// Applies the release kill switch when an analytics flag context is usable.
bool shouldDisableCustomLiveAudioRecovery({
  required bool buildEnabled,
  required bool flagReadContextAvailable,
  required bool? cachedKillSwitchEnabled,
  bool unresolvedRetryExhausted = false,
}) =>
    resolveCustomLiveAudioRecoveryGate(
      buildEnabled: buildEnabled,
      flagReadContextAvailable: flagReadContextAvailable,
      cachedKillSwitchEnabled: cachedKillSwitchEnabled,
      unresolvedRetryExhausted: unresolvedRetryExhausted,
    ) !=
    CustomLiveAudioRecoveryGate.enabled;
