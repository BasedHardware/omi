import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/messages.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:uuid/uuid.dart';

class NoDeviceChatProvider extends ChangeNotifier {
  List<ServerMessage> messages = [];
  bool isLoadingMessages = false;
  bool hasCachedMessages = false;
  bool isClearingChat = false;
  bool showTypingIndicator = false;
  bool sendingMessage = false;
  String firstTimeLoadingText = '';

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
      firstTimeLoadingText = 'Reading your messages...';
      notifyListeners();
    }
    setLoadingMessages(true);
    var mes = await getMessagesServerV3();
    if (!hasCachedMessages) {
      firstTimeLoadingText = 'Processing your messages...';
      notifyListeners();
    }
    messages = mes;
    setLoadingMessages(false);
    notifyListeners();
    return messages;
  }

  Future clearChat() async {
    setClearingChat(true);
    var mes = await clearChatServerV3();
    messages = mes;
    setClearingChat(false);
    notifyListeners();
  }

  void addMessage(ServerMessage message) {
    if (messages.any((m) => m.id == message.id)) {
      return;
    }
    messages.insert(0, message);
    notifyListeners();
  }

  Future sendMessageStreamToServer(String text) async {
    setShowTypingIndicator(true);
    ServerMessage? message;
    notifyListeners();

    try {
      await for (var chunk in sendMessageStreamServerV3(text)) {
        if (chunk.type == MessageChunkType.think) {
          if (message == null) {
            message = ServerMessage.empty();
            messages.insert(0, message);
          }
          message.thinkings.add(chunk.text);
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.data) {
          if (message == null) {
            message = ServerMessage.empty();
            messages.insert(0, message);
          }
          setShowTypingIndicator(false);
          message.text += chunk.text;
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.done) {
          if (message != null) {
            messages[0] = chunk.message!;
          } else {
            messages.insert(0, chunk.message!);
          }
          notifyListeners();
          continue;
        }

        if (chunk.type == MessageChunkType.error) {
          if (message == null) {
            message = ServerMessage.empty();
            messages.insert(0, message);
          }
          message.text = chunk.text;
          notifyListeners();
          continue;
        }
      }
    } catch (e) {
      if (message == null) {
        message = ServerMessage.empty();
        messages.insert(0, message);
      }
      message.text = ServerMessageChunk.failedMessage().text;
      notifyListeners();
    }

    setShowTypingIndicator(false);
  }

  Future sendMessageToServer(String text) async {
    final message = ServerMessage(
      const Uuid().v4(),
      DateTime.now(),
      text,
      MessageSender.human,
      MessageType.text,
      null,
      false,
      [],
    );
    messages.insert(0, message);
    notifyListeners();
    await sendMessageStreamToServer(text);
  }
} 