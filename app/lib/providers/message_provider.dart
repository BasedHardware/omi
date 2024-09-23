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
  bool hasCachedMessages = false;
  bool isClearingChat = false;

  String firstTimeLoadingText = '';

  void updatePluginProvider(PluginProvider p) {
    pluginProvider = p;
  }

  void setHasCachedMessages(bool value) {
    hasCachedMessages = value;
    notifyListeners();
  }

  void setClearingChat(bool value) {
    isClearingChat = value;
    notifyListeners();
  }

  void setLoadingMessages(bool value) {
    isLoadingMessages = value;
    notifyListeners();
  }

  Future refreshMessages() async {
    setLoadingMessages(true);
    if (SharedPreferencesUtil().cachedMessages.isNotEmpty) {
      setHasCachedMessages(true);
    }
    messages = await getMessagesFromServer();
    if (messages.isEmpty) {
      messages = SharedPreferencesUtil().cachedMessages;
    } else {
      SharedPreferencesUtil().cachedMessages = messages;
      setHasCachedMessages(true);
    }
    setLoadingMessages(false);
    notifyListeners();
  }

  void setMessagesFromCache() {
    if (SharedPreferencesUtil().cachedMessages.isNotEmpty) {
      setHasCachedMessages(true);
      messages = SharedPreferencesUtil().cachedMessages;
    }
    notifyListeners();
  }

  Future<List<ServerMessage>> getMessagesFromServer() async {
    if (!hasCachedMessages) {
      firstTimeLoadingText = 'Reading your memories...';
      notifyListeners();
    }
    setLoadingMessages(true);
    var mes = await getMessagesServer();
    if (!hasCachedMessages) {
      firstTimeLoadingText = 'Learning from your memories...';
      notifyListeners();
    }
    messages = mes;
    setLoadingMessages(false);
    notifyListeners();
    return messages;
  }

  Future clearChat() async {
    setClearingChat(true);
    var mes = await clearChatServer();
    messages = mes;
    setClearingChat(false);
    notifyListeners();
  }

  void addMessage(ServerMessage message) {
    messages.insert(0, message);
    notifyListeners();
  }

  Future sendMessageToServer(String message, String? pluginId) async {
    var mes = await sendMessageServer(message, pluginId: pluginId);
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
