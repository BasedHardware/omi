import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:friend_private/backend/http/api/messages.dart';
import 'package:friend_private/backend/http/api/users.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/backend/schema/chat_session.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/file.dart';
import 'package:friend_private/utils/logger.dart';

class MessageProvider extends ChangeNotifier {
  AppProvider? appProvider;
  List<ServerMessage> messages = [];

  List<ChatSession> _chatSessions = [];
  String? _currentSessionId;
  bool _isLoadingSessions = false;

  bool isLoadingMessages = false;
  bool hasCachedMessages = false;
  bool isClearingChat = false;
  bool showTypingIndicator = false;
  bool sendingMessage = false;

  String firstTimeLoadingText = '';

  List<ChatSession> get chatSessions => _chatSessions;
  String? get currentSessionId => _currentSessionId;
  bool get isLoadingSessions => _isLoadingSessions;
  ChatSession? get currentSession => _currentSessionId != null 
      ? _chatSessions.firstWhereOrNull((s) => s.id == _currentSessionId)
      : null;

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

  void removeLocalMessage(String id) {
    messages.removeWhere((m) => m.id == id);
    notifyListeners();
  }

 Future refreshMessages({bool dropdownSelected = false}) async {
  if (_currentSessionId == null) return;
  
  setLoadingMessages(true);
  
  // Check for cached messages for this session
  if (SharedPreferencesUtil().cachedMessages.isNotEmpty) {
    setHasCachedMessages(true);
  }

  try {
    // Get messages for current session
    final sessionMessages = await getSessionMessagesServer(_currentSessionId!);
    
    if (sessionMessages.isNotEmpty) {
      messages = sessionMessages;
      SharedPreferencesUtil().cachedMessages = messages;
      setHasCachedMessages(true);
    } else if (messages.isEmpty) {
      // If no server messages, use cached messages
      messages = SharedPreferencesUtil().cachedMessages;
    }
  } catch (e) {
    Logger.error('Error refreshing session messages: $e');
    // On error, fall back to cached messages
    if (messages.isEmpty) {
      messages = SharedPreferencesUtil().cachedMessages;
    }
  } finally {
    setLoadingMessages(false);
    notifyListeners();
  }
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
    if (messages.firstWhereOrNull((m) => m.id == message.id) != null) {
      return;
    }
    messages.insert(0, message);
    notifyListeners();
  }

  Future sendVoiceMessageStreamToServer(List<List<int>> audioBytes, {Function? onFirstChunkRecived}) async {
    var file = await FileUtils.saveAudioBytesToTempFile(
      audioBytes,
      DateTime.now().millisecondsSinceEpoch ~/ 1000 - (audioBytes.length / 100).ceil(),
    );

    setShowTypingIndicator(true);
    var message = ServerMessage.empty();
    messages.insert(0, message);
    notifyListeners();

    try {
      bool firstChunkRecieved = false;
      await for (var chunk in sendVoiceMessageStreamServer([file])) {
        if (!firstChunkRecieved && [MessageChunkType.data, MessageChunkType.done].contains(chunk.type)) {
          firstChunkRecieved = true;
          if (onFirstChunkRecived != null) {
            onFirstChunkRecived();
          }
        }

        if (chunk.type == MessageChunkType.think) {
          message.thinkings.add(chunk.text);
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.data) {
          message.text += chunk.text;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.done) {
          message = chunk.message!;
          messages[0] = message;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.message) {
          messages.insert(1, chunk.message!);
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.error) {
          message.text = chunk.text;
          notifyListeners();
          continue;
        }
      }
    } catch (e) {
      message.text = ServerMessageChunk.failedMessage().text;
      notifyListeners();
    }

    setShowTypingIndicator(false);
  }

  Future sendMessageStreamToServer(String text, String? appId) async {
    if (_currentSessionId == null) {
      await createNewChat();
    }
  
    setShowTypingIndicator(true);
    var message = ServerMessage.empty(appId: appId);
    messages.insert(0, message);
    notifyListeners();

    try {
      await for (var chunk in sendMessageStreamServer(text, appId: appId, sessionId: _currentSessionId)) {
        debugPrint('Received chunk type: ${chunk.type}');
        
        if (chunk.type == MessageChunkType.think) {
          message.thinkings.add(chunk.text);
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.data) {
          message.text += chunk.text;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.done) {
          message = chunk.message!;
          messages[0] = message;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.error) {
          message.text = chunk.text;
          notifyListeners();
          continue;
        }
      }
    } catch (e) {
      message.text = ServerMessageChunk.failedMessage().text;
      notifyListeners();
    }

    setShowTypingIndicator(false);
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

  Future<void> loadChatSessions() async {
    _isLoadingSessions = true;
    notifyListeners();

    try {
      final sessions = await getChatSessionsServer();
      _chatSessions = sessions;

      // If no current session, set to most recent
      if (_currentSessionId == null && sessions.isNotEmpty) {
        _currentSessionId = sessions.first.id;
      }
    } catch (e) {
      Logger.error('Error loading chat sessions: $e');
    } finally {
      _isLoadingSessions = false;
      notifyListeners();
    }
  }

  Future<void> createNewChat() async {
    try {
      final newSession = await createChatSessionServer(
        pluginId: appProvider?.selectedChatAppId
      );
      
      if (newSession != null) {
        _chatSessions.insert(0, newSession);
        _currentSessionId = newSession.id;
        messages.clear(); // Clear current messages
        notifyListeners();
      }
    } catch (e) {
      Logger.error('Error creating new chat: $e');
    }
  }

  Future<void> loadChatSession(String sessionId) async {
    if (sessionId == _currentSessionId) return;

    setHasCachedMessages(false);
    setLoadingMessages(true);

    if(isLoadingMessages) {
      firstTimeLoadingText = 'Loading your chat...';
    }

    try {
      _currentSessionId = sessionId;
      messages = await getSessionMessagesServer(sessionId) ?? [];
      SharedPreferencesUtil().cachedMessages = messages;
      setHasCachedMessages(true);
    } catch (e) {
      Logger.error('Error loading chat session: $e');
    } finally {
      setLoadingMessages(false);
      setHasCachedMessages(true);
      notifyListeners();
    }
  }

  Future<void> deleteChatSession(String sessionId) async {
    try {
      final success = await deleteChatSessionServer(sessionId);
      
      if (success) {
        _chatSessions.removeWhere((s) => s.id == sessionId);
        
        // If current session was deleted, switch to most recent
        if (sessionId == _currentSessionId && _chatSessions.isNotEmpty) {
          await loadChatSession(_chatSessions.first.id);
        } else if (_chatSessions.isEmpty) {
          _currentSessionId = null;
          messages.clear();
        }
        notifyListeners();
      }
    } catch (e) {
      Logger.error('Error deleting chat session: $e');
    }
  }

  Future<void> renameChatSession(String sessionId, String newName) async {
    try {
      final updatedSession = await updateChatSessionServer(
        sessionId, 
        {'title': newName}
      );
      
      if (updatedSession != null) {
        final index = _chatSessions.indexWhere((s) => s.id == sessionId);
        if (index != -1) {
          _chatSessions[index] = updatedSession;
          notifyListeners();
        }
      }
    } catch (e) {
      Logger.error('Error renaming chat session: $e');
    }
  }
}
