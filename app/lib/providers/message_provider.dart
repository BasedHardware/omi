import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:friend_private/backend/http/api/messages.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/backend/schema/message.dart';
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

  Future refreshMessages({bool dropdownSelected = false}) async {
    setLoadingMessages(true);
    if (SharedPreferencesUtil().cachedMessages.isNotEmpty) {
      setHasCachedMessages(true);
    }
    messages = await getMessagesFromServer(dropdownSelected: dropdownSelected);
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

  Future<List<ServerMessage>> getMessagesFromServer({bool dropdownSelected = false}) async {
    print('getMessagesFromServer');
    if (!hasCachedMessages) {
      firstTimeLoadingText = 'Reading your memories...';
      notifyListeners();
    }
    setLoadingMessages(true);
    print('appProvider?.selectedChatAppId: ${appProvider?.selectedChatAppId}');
    var mes = await getMessagesServer(
      pluginId: appProvider?.selectedChatAppId,
      dropdownSelected: dropdownSelected,
    );
    if (!hasCachedMessages) {
      firstTimeLoadingText = 'Learning from your memories...';
      notifyListeners();
    }
    messages = mes;
    setLoadingMessages(false);
    notifyListeners();
    return messages;
  }

  Future setMessageNps(ServerMessage message, int value) async {
    await setMessageResponseRating(message.id, value);
    message.askForNps = false;
    notifyListeners();
  }

  Future clearChat() async {
    setClearingChat(true);
    var mes = await clearChatServer(pluginId: appProvider?.selectedChatAppId);
    messages = mes;
    setClearingChat(false);
    notifyListeners();
  }

  void addMessage(ServerMessage message) {
    messages.insert(0, message);
    notifyListeners();
  }

  Future sendMessageToServer(String message, String? appId) async {
    setShowTypingIndicator(true);
    messages.insert(0, ServerMessage.empty(appId: appId));
    var mes = await sendMessageServer(message, appId: appId);
    if (messages[0].id == '0000') {
      messages[0] = mes;
    }
    setShowTypingIndicator(false);
    notifyListeners();
  }

  Future sendInitialAppMessage(App? app) async {
    setSendingMessage(true);
    ServerMessage message = await getInitialAppMessage(app?.id);
    addMessage(message);
    setSendingMessage(false);
    notifyListeners();
  }

  App? messageSenderApp(String? appId) {
    return appProvider?.apps.firstWhereOrNull((p) => p.id == appId);
  }
}
