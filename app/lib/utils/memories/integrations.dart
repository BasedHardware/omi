import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/utils/other/notifications.dart';
import 'package:tuple/tuple.dart';

getOnMemoryCreationEvents(Memory memory) async {
  var onMemoryCreationPlugins = SharedPreferencesUtil()
      .pluginsList
      .where((element) => element.externalIntegration?.triggersOn == 'memory_creation' && element.enabled)
      .toSet()
      .toList();
  // print('onMemoryCreationPlugins: $onMemoryCreationPlugins');
  List<Future<Tuple2<Plugin, String>>> triggerPluginResult = onMemoryCreationPlugins.map((plugin) async {
    var url = plugin.externalIntegration!.webhookUrl;
    // var url = 'https://eddc-148-64-106-26.ngrok-free.app/notion-crm';
    String message = await triggerMemoryRequestAtEndpoint(url, memory);
    return Tuple2(plugin, message);
  }).toList();
  return await Future.wait(triggerPluginResult);
}

getOnTranscriptSegmentReceivedEvents(List<TranscriptSegment> segment, String sessionId) async {
  var plugins = SharedPreferencesUtil()
      .pluginsList
      .where((element) => element.externalIntegration?.triggersOn == 'transcript_processed' && element.enabled)
      .toSet()
      .toList();
  List<Future<Tuple2<Plugin, String>>> triggerPluginResult = plugins.map((plugin) async {
    var url = plugin.externalIntegration!.webhookUrl;
    String message = await triggerTranscriptSegmentsRequest(url, sessionId, segment);
    return Tuple2(plugin, message);
  }).toList();
  return await Future.wait(triggerPluginResult);
}

triggerMemoryCreatedEvents(
  Memory memory, {
  Function(Message, Memory?)? sendMessageToChat,
}) async {
  if (memory.discarded) return;

  webhookOnMemoryCreatedCall(memory).then((s) {
    if (s.isNotEmpty) createNotification(title: 'Developer: On Memory Created', body: s, notificationId: 10);
  });

  List<Tuple2<Plugin, String>> results = await getOnMemoryCreationEvents(memory);
  for (var result in results) {
    if (result.item2.isNotEmpty) {
      createNotification(title: '${result.item1.name} says', body: result.item2, notificationId: result.item1.hashCode);
      if (sendMessageToChat != null) {
        sendMessageToChat(
          Message(DateTime.now(), result.item2, 'ai', pluginId: result.item1.id, fromIntegration: true),
          null,
        );
      }
    }
  }
}

triggerTranscriptSegmentReceivedEvents(
  List<TranscriptSegment> segments,
  String sessionId, {
  Function(Message, Memory?)? sendMessageToChat,
}) async {
  webhookOnTranscriptReceivedCall(segments, sessionId).then((s) {
    if (s.isNotEmpty) createNotification(title: 'Developer: On Transcript Received', body: s, notificationId: 10);
  });
  List<Tuple2<Plugin, String>> results = await getOnTranscriptSegmentReceivedEvents(segments, sessionId);
  for (var result in results) {
    if (result.item2.isNotEmpty) {
      createNotification(title: '${result.item1.name} says', body: result.item2, notificationId: result.item1.hashCode);
      if (sendMessageToChat != null) {
        // send memory to be created maybe
        sendMessageToChat(
          Message(DateTime.now(), result.item2, 'ai', pluginId: result.item1.id, fromIntegration: true),
          null,
        );
      }
    }
  }
}
