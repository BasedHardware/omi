// Pigeon contracts are build-time inputs; the package is a dev dependency.
// ignore: depend_on_referenced_packages
import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(
  PigeonOptions(
    dartOut: 'lib/gen/siri_pigeon.g.dart',
    swiftOut: 'ios/Runner/SiriIntegration/SiriPigeon.g.swift',
    swiftOptions: SwiftOptions(errorClassName: 'SiriPigeonError'),
    dartPackageName: 'omi_siri',
  ),
)
class SiriConversation {
  String id;
  String title;
  String summary;
  int startedAtMs;
  int updatedAtMs;
  SiriConversation(this.id, this.title, this.summary, this.startedAtMs, this.updatedAtMs);
}

class SiriMemory {
  String id;
  String content;
  int createdAtMs;
  int? expiresAtMs;
  SiriMemory(this.id, this.content, this.createdAtMs, this.expiresAtMs);
}

class SiriTask {
  String id;
  String title;
  bool completed;
  int createdAtMs;
  int? dueAtMs;
  int? completedAtMs;
  SiriTask(this.id, this.title, this.completed, this.createdAtMs, this.dueAtMs, this.completedAtMs);
}

class SiriSessionConfig {
  String uid;
  int generation;
  String baseUrl;
  String profile;
  String appVersion;
  String appBuild;
  String deviceIdHash;
  String? token;
  int? tokenExpiresAtMs;
  SiriSessionConfig(this.uid, this.generation, this.baseUrl, this.profile, this.appVersion, this.appBuild,
      this.deviceIdHash, this.token, this.tokenExpiresAtMs);
}

class SiriTelemetryRecord {
  String kind;
  String intent;
  String outcome;
  int latencyMs;
  int entityCounts;
  String entryPath;
  SiriTelemetryRecord(this.kind, this.intent, this.outcome, this.latencyMs, this.entityCounts, this.entryPath);
}

class SiriPendingRoute {
  String route;
  String uid;
  int generation;
  SiriPendingRoute(this.route, this.uid, this.generation);
}

@HostApi()
abstract class SiriIndexApi {
  @async
  void upsertConversations(String uid, List<SiriConversation> conversations);

  /// Replace only the authoritative time window; null covers all conversations.
  @async
  void reconcileConversations(String uid, List<SiriConversation> conversations, int? coveredAfterMs);
  @async
  void upsertMemories(String uid, List<SiriMemory> memories);

  /// Called only after a complete, unfiltered owner memory fetch.
  @async
  void reconcileMemories(String uid, List<SiriMemory> memories);
  @async
  void upsertTasks(String uid, List<SiriTask> tasks);

  /// A complete active-only fetch preserves completed rows when false.
  @async
  void reconcileTasks(String uid, List<SiriTask> tasks, bool includeCompleted);
  @async
  void deleteEntities(String uid, String type, List<String> ids);

  /// Clear one owner's persisted snapshot and Spotlight index before a fresh authoritative traversal.
  @async
  void repairOwnerIndex(String uid);
  @async
  int wipe();

  /// Durably block engine-free Siri and clear its token before Firebase signs out.
  @async
  void prepareForSignOut();

  /// Reuse the persisted index generation only when its snapshot still belongs to this UID.
  @async
  int? generationForOwner(String uid);
  @async
  void setEnabled(bool enabled);
  void setCurrentScreen(String route, String? entityId);
  @async
  void publishSessionConfig(SiriSessionConfig config);
  SiriPendingRoute? takePendingRoute();
  void finishPendingRoute(String route, String uid, int generation, bool delivered);
  bool isEnabled();
  List<SiriTelemetryRecord> takeTelemetry();

  /// True only when the Runner was compiled with the Siri toolchain, so Dart can
  /// skip App Shortcuts UI (e.g. the Shortcuts button) in stable-compiler builds.
  bool appShortcutsAvailable();
  @async
  void donateAction(String uid, String type, String id);
}

@FlutterApi()
abstract class SiriEventsApi {
  void memoryCreated(String id);
  void taskChanged(String id);
  @async
  bool openRoute(String route, String uid, int generation);
  @async
  void setListening(bool enabled);
}
