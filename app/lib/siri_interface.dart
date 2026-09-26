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
  String baseUrl;
  String profile;
  String appVersion;
  String appBuild;
  String deviceIdHash;
  String? token;
  int? tokenExpiresAtMs;
  SiriSessionConfig(this.uid, this.baseUrl, this.profile, this.appVersion, this.appBuild, this.deviceIdHash, this.token,
      this.tokenExpiresAtMs);
}

class SiriTelemetryRecord {
  String kind;
  String intent;
  String outcome;
  int latencyMs;
  int entityCounts;
  SiriTelemetryRecord(this.kind, this.intent, this.outcome, this.latencyMs, this.entityCounts);
}

@HostApi()
abstract class SiriIndexApi {
  @async
  void upsertConversations(String uid, List<SiriConversation> conversations);
  @async
  void upsertMemories(String uid, List<SiriMemory> memories);
  @async
  void upsertTasks(String uid, List<SiriTask> tasks);
  @async
  void deleteEntities(String uid, String type, List<String> ids);
  @async
  void wipe();
  @async
  void setEnabled(bool enabled);
  void setCurrentScreen(String route, String? entityId);
  @async
  void publishSessionConfig(SiriSessionConfig config);
  String? takePendingRoute();
  bool isEnabled();
  List<SiriTelemetryRecord> takeTelemetry();
  @async
  void donateAction(String uid, String type, String id);
}

@FlutterApi()
abstract class SiriEventsApi {
  void memoryCreated(String id);
  void taskChanged(String id);
  void openRoute(String route);
  @async
  void setListening(bool enabled);
}
