import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:friend_private/backend/http/api/messages.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/providers/app_provider.dart';

class MessageProvider extends ChangeNotifier {
  AppProvider? appProvider;
  List<ServerMessage> messages = [];

  bool isLoadingMessages = false;
  bool hasCachedMessages = false;
  bool isClearingChat = false;
  bool showTypingIndicator = false;
  bool sendingMessage = false;

  String firstTimeLoadingText = '';

  void updateAppProvider(AppProvider p) {
    appProvider = p;
  }

  void setHasCachedMessages(bool value) {
    hasCachedMessages = value;
    notifyListeners();
  }

  void setSendingMessage(bool value) {
    sendingMessage = value;
    notifyListeners();
  }

  void setShowTypingIndicator(bool value) {
    showTypingIndicator = value;
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
    setShowTypingIndicator(true);
    messages.insert(0, ServerMessage.empty());
    var mes = await sendMessageServer(message, pluginId: pluginId);
    if (messages[0].id == '0000') {
      messages[0] = mes;
    }
    setShowTypingIndicator(false);
    notifyListeners();
  }

  Future sendInitialPluginMessage(App? plugin) async {
    setSendingMessage(true);
    ServerMessage message = await getInitialPluginMessage(plugin?.id);
    addMessage(message);
    setSendingMessage(false);
    notifyListeners();
  }

  void checkSelectedPlugins() {
    var selectedChatPlugin = SharedPreferencesUtil().selectedChatPluginId;
    debugPrint('_edgeCasePluginNotAvailable $selectedChatPlugin');
    var plugin = appProvider!.apps.firstWhereOrNull((p) => selectedChatPlugin == p.id);
    if (selectedChatPlugin != 'no_selected' && (plugin == null || !plugin.worksWithChat() || !plugin.enabled)) {
      SharedPreferencesUtil().selectedChatPluginId = 'no_selected';
    }
    notifyListeners();
  }
}
