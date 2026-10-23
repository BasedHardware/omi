import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/logger.dart';

/// PostHog owns the cohort. Unknown values keep the old serving behavior.
abstract final class ClientRefactorFlags {
  static bool get serving => AnalyticsManager().refactorClientsEnabled(_ClientProjection.enabledFlag);
  static Future<bool> chunkUploads() => AnalyticsManager().isBooleanFeatureEnabled(_SegmentChunks.enabledFlag);
  // Data release is an opt-in, never a default-on kill switch.
  static Future<bool> custodyRelease() => AnalyticsManager().isBooleanFeatureEnabled(_CustodyRelease.enabledFlag);

  static void compare(String check, bool agrees) {
    if (!agrees) Logger.debug('event=refactor_shadow lane=L5 check=$check outcome=disagree');
  }
}

// Named enable keys keep the repository flag inventory mechanically discoverable.
abstract final class _ClientProjection {
  static const enabledFlag = 'clients_refactor';
}

abstract final class _SegmentChunks {
  static const enabledFlag = 'clients_from_segments_chunks';
}

abstract final class _CustodyRelease {
  static const enabledFlag = 'custody_capture_committed_release';
}
