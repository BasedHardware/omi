import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/logger.dart';

/// PostHog owns the cohort. Unknown values keep the old serving behavior.
abstract final class ClientRefactorFlags {
  static const clients = 'clients_refactor';
  static const chunks = 'clients_from_segments_chunks';
  static const custody = 'custody_capture_committed_release';

  static bool get serving => AnalyticsManager().refactorClientsEnabled(clients);
  static Future<bool> chunkUploads() => AnalyticsManager().isBooleanFeatureEnabled(chunks);
  // Data release is an opt-in, never a default-on kill switch.
  static Future<bool> custodyRelease() => AnalyticsManager().isBooleanFeatureEnabled(custody);

  static void compare(String check, bool agrees) {
    Logger.debug('event=refactor_shadow lane=L5 check=$check outcome=${agrees ? 'agree' : 'disagree'}');
  }
}
