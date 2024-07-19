import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/utils/other/notifications.dart';
import 'package:tuple/tuple.dart';

getOnMemoryCreationEvents(Memory memory) async {
  var onMemoryCreationPlugins = SharedPreferencesUtil()
      .pluginsList
      .where((element) => element.externalIntegration?.triggersOn == 'memory_creation' && element.enabled)
      .toList();
  // print('onMemoryCreationPlugins: $onMemoryCreationPlugins');
  List<Future<Tuple2<Plugin, String>>> triggerPluginResult = onMemoryCreationPlugins.map((plugin) async {
    var url = plugin.externalIntegration!.webhookUrl;
    // var url = 'https://eddc-148-64-106-26.ngrok-free.app/notion-crm';
    if (url.contains('?')) {
      url += '&uid=${SharedPreferencesUtil().uid}';
    } else {
      url += '?uid=${SharedPreferencesUtil().uid}';
    }
    String message = await triggerMemoryRequestAtEndpoint(url, memory);
    return Tuple2(plugin, message);
  }).toList();
  return await Future.wait(triggerPluginResult);
}

getOnTranscriptSegmentReceivedEvents(List<TranscriptSegment> segment, String sessionId) async {
  var plugins = SharedPreferencesUtil()
      .pluginsList
      .where((element) => element.externalIntegration?.triggersOn == 'transcript_processed' && element.enabled)
      .toList();
  List<Future<Tuple2<Plugin, String>>> triggerPluginResult = plugins.map((plugin) async {
    var url = plugin.externalIntegration!.webhookUrl;
    // var url = 'https://610e-148-64-106-26.ngrok-free.app/news-checker';
    if (url.contains('?')) {
      url += '&uid=${SharedPreferencesUtil().uid}';
    } else {
      url += '?uid=${SharedPreferencesUtil().uid}';
    }
    String message = await triggerTranscriptSegmentsRequest(url, sessionId, segment);
    return Tuple2(plugin, message);
  }).toList();
  return await Future.wait(triggerPluginResult);
}

triggerMemoryCreatedEvents(Memory memory) async {
  if (memory.discarded) return;

  devModeWebhookCall(memory).then((s) {
    if (s.isNotEmpty) createNotification(title: 'Webhook Result', body: s, notificationId: 10);
  });

  List<Tuple2<Plugin, String>> results = await getOnMemoryCreationEvents(memory);
  for (var result in results) {
    if (result.item2.isNotEmpty) {
      createNotification(title: '${result.item1.name} says', body: result.item2, notificationId: result.item1.hashCode);
    }
  }
}

triggerTranscriptSegmentReceivedEvents(List<TranscriptSegment> segments, String sessionId) async {
  List<Tuple2<Plugin, String>> results = await getOnTranscriptSegmentReceivedEvents(segments, sessionId);
  for (var result in results) {
    if (result.item2.isNotEmpty) {
      createNotification(title: '${result.item1.name} says', body: result.item2, notificationId: result.item1.hashCode);
    }
  }
}
