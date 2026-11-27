/// Fails closed when the cached release kill switch cannot be read.
bool shouldDisableCustomLiveAudioRecovery({
  required bool buildEnabled,
  required bool analyticsTrackingEnabled,
  required bool identitySettled,
  required bool cachedKillSwitchEnabled,
}) =>
    !buildEnabled || !analyticsTrackingEnabled || !identitySettled || cachedKillSwitchEnabled;
