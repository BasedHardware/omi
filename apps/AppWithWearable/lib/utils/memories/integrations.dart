import 'package:friend_private/backend/api_requests/api/other.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/utils/other/notifications.dart';
import 'package:tuple/tuple.dart';

triggerMemoryCreatedEvents(Memory memory) async {
  if (memory.discarded) return;

  devModeWebhookCall(memory).then((s) {
    if (s.isNotEmpty) createNotification(title: 'Webhook Result', body: s, notificationId: 10);
  });
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

  List<Tuple2<Plugin, String>> results = await Future.wait(triggerPluginResult);
  for (var result in results) {
    if (result.item2.isNotEmpty) {
      createNotification(title: '${result.item1.name} says', body: result.item2, notificationId: result.item1.hashCode);
    }
  }
}
