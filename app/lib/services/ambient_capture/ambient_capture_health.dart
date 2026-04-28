enum AmbientCaptureHealthState {
  audioOk('AUDIO_OK'),
  audioSilencedBySystem('AUDIO_SILENCED_BY_SYSTEM'),
  audioLowSignal('AUDIO_LOW_SIGNAL'),
  callOrCommunicationMode('CALL_OR_COMMUNICATION_MODE'),
  highRiskAppActive('HIGH_RISK_APP_ACTIVE'),
  networkDownBuffering('NETWORK_DOWN_BUFFERING'),
  textOnlyFallback('TEXT_ONLY_FALLBACK'),
  privateMode('PRIVATE_MODE'),
  pausedByUser('PAUSED_BY_USER'),
  policyDisabled('POLICY_DISABLED'),
  permissionMissing('PERMISSION_MISSING'),
  accessibilityDisabled('ACCESSIBILITY_DISABLED'),
  serviceKilled('SERVICE_KILLED'),
  recoveryNeeded('RECOVERY_NEEDED'),
  unknownDegraded('UNKNOWN_DEGRADED');

  final String wireName;
  const AmbientCaptureHealthState(this.wireName);

  static AmbientCaptureHealthState fromWire(String? value) {
    return AmbientCaptureHealthState.values.firstWhere(
      (state) => state.wireName == value,
      orElse: () => AmbientCaptureHealthState.unknownDegraded,
    );
  }
}

class AmbientCaptureHealth {
  final AmbientCaptureHealthState state;
  final double? dbfs;
  final double? zeroFrameRatio;
  final String? foregroundPackage;
  final String? audioMode;
  final bool networkAvailable;
  final bool socketConnected;
  final int walQueueDepth;
  final DateTime timestamp;
  final String? reason;

  const AmbientCaptureHealth({
    required this.state,
    this.dbfs,
    this.zeroFrameRatio,
    this.foregroundPackage,
    this.audioMode,
    this.networkAvailable = true,
    this.socketConnected = false,
    this.walQueueDepth = 0,
    required this.timestamp,
    this.reason,
  });

  factory AmbientCaptureHealth.fromJson(Map<dynamic, dynamic> json) {
    final millis = json['timestamp'] is int ? json['timestamp'] as int : DateTime.now().millisecondsSinceEpoch;
    return AmbientCaptureHealth(
      state: AmbientCaptureHealthState.fromWire(json['state']?.toString()),
      dbfs: (json['dbfs'] as num?)?.toDouble(),
      zeroFrameRatio: (json['zeroFrameRatio'] as num?)?.toDouble(),
      foregroundPackage: json['foregroundPackage']?.toString(),
      audioMode: json['audioMode']?.toString(),
      networkAvailable: json['networkAvailable'] as bool? ?? true,
      socketConnected: json['socketConnected'] as bool? ?? false,
      walQueueDepth: (json['walQueueDepth'] as num?)?.toInt() ?? 0,
      timestamp: DateTime.fromMillisecondsSinceEpoch(millis),
      reason: json['reason']?.toString(),
    );
  }
}
