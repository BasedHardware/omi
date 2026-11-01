/// Client reliability-telemetry switches. Both default off.
///
/// Parent owns activation after a real collector and seven closed UTC canary
/// days. This lane must not enable either flag.
class ClientTelemetryFlags {
  ClientTelemetryFlags._();

  static const migrationEnabledFromEnvironment = bool.fromEnvironment('OMI_CLIENT_TELEMETRY_MIGRATION');
  static const posthogRetirementEnabledFromEnvironment = bool.fromEnvironment(
    'OMI_CLIENT_TELEMETRY_POSTHOG_RETIREMENT',
  );

  /// Test-only override. Production leaves this null so the compile-time
  /// default (false) holds.
  static bool? migrationEnabledOverride;

  /// Test-only override. Independent of [migrationEnabledOverride].
  static bool? posthogRetirementEnabledOverride;

  /// When true, reliability observations are also written to the durable
  /// outbox. PostHog emission of those events continues until retirement.
  static bool get migrationEnabled => migrationEnabledOverride ?? migrationEnabledFromEnvironment;

  /// When true, PostHog copies of moved infrastructure events stop.
  /// Device Connected, Device Disconnected Detailed, Recording Requested,
  /// and product events are not retired by this flag.
  static bool get posthogRetirementEnabled =>
      posthogRetirementEnabledOverride ?? posthogRetirementEnabledFromEnvironment;

  static void debugReset() {
    migrationEnabledOverride = null;
    posthogRetirementEnabledOverride = null;
  }
}
