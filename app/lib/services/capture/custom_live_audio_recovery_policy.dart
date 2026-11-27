/// Applies the release kill switch when an analytics flag context is usable.
bool shouldDisableCustomLiveAudioRecovery({
  required bool buildEnabled,
  required bool flagReadContextAvailable,
  required bool? cachedKillSwitchEnabled,
}) =>
    !buildEnabled || cachedKillSwitchEnabled == true || (flagReadContextAvailable && cachedKillSwitchEnabled == null);
