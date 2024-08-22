import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:friend_private/backend/http/api/messages.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/providers/plugin_provider.dart';

class MessageProvider extends ChangeNotifier {
  PluginProvider? pluginProvider;
  List<ServerMessage> messages = [];

  bool isLoadingMessages = false;

  void updatePluginProvider(PluginProvider p) {
    pluginProvider = p;
  }

  void setLoadingMessages(bool value) {
    isLoadingMessages = value;
    notifyListeners();
  }

  Future refreshMessages() async {
    setLoadingMessages(true);
    messages = await getMessagesFromServer();
    if (messages.isEmpty) {
      messages = SharedPreferencesUtil().cachedMessages;
    } else {
      SharedPreferencesUtil().cachedMessages = messages;
    }
    setLoadingMessages(false);
    notifyListeners();
  }

  Future<List<ServerMessage>> getMessagesFromServer() async {
    setLoadingMessages(true);
    var mes = await getMessagesServer();
    messages = mes;
    setLoadingMessages(false);
    notifyListeners();
    return messages;
  }

  void addMessage(ServerMessage message) {
    messages.insert(0, message);
    notifyListeners();
  }

  Future sendMessageToServer(String message, String? pluginId) async {
    var mes = await sendMessageServer(message);
    messages.insert(0, mes);
    notifyListeners();
  }

  void checkSelectedPlugins() {
    var selectedChatPlugin = SharedPreferencesUtil().selectedChatPluginId;
    debugPrint('_edgeCasePluginNotAvailable $selectedChatPlugin');
    var plugin = pluginProvider!.plugins.firstWhereOrNull((p) => selectedChatPlugin == p.id);
    if (selectedChatPlugin != 'no_selected' && (plugin == null || !plugin.worksWithChat() || !plugin.enabled)) {
      SharedPreferencesUtil().selectedChatPluginId = 'no_selected';
    }
    notifyListeners();
  }
}
