import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/platform/floating_chat_service.dart';

class FloatingChatProvider with ChangeNotifier {
  StreamSubscription? _messageSubscription;
  final MessageProvider _messageProvider;

  FloatingChatProvider(this._messageProvider) {
    initialize();
  }

  void initialize() {
    // Ensure the service is ready to handle method calls from Swift.
    FloatingChatService.init();
    _messageSubscription?.cancel();
    _messageSubscription = FloatingChatService.onMessageReceived.listen(_handleMessageFromSwift);
    print("FloatingChatProvider initialized.");
  }

  Future<void> _handleMessageFromSwift(Map<String, dynamic> message) async {
    final type = message['type'] as String?;
    if (type == 'requestHistory') {
      await _handleHistoryRequest(message);
    } else {
      await _handleUserMessage(message);
    }
  }

  Future<void> _handleHistoryRequest(Map<String, dynamic> message) async {
    final conversationId = message['conversationId'];
    print("FloatingChatProvider received history request for: $conversationId");
    // TODO: Integrate with MessageProvider to get actual history.

    // For now, sending dummy history.
    final dummyHistory = {
      'conversationId': conversationId,
      'history': [
        {'text': 'Hello from the past!', 'type': 'ai'},
        {'text': 'Hi, I am a user.', 'type': 'user'},
        {'text': 'This is a dummy history record.', 'type': 'ai'},
      ],
    };

    await FloatingChatService.sendChatHistory(dummyHistory);
  }

  Future<void> _handleUserMessage(Map<String, dynamic> message) async {
    print("FloatingChatProvider received message from Swift: $message");

    final text = message['text'] as String? ?? '';
    final conversationId = message['conversationId'];
    final attachmentPath = message['attachmentPath'] as String?;
    List<String>? fileIds;

    if (attachmentPath != null) {
      print("Attachment received at path: $attachmentPath");
      final uploadedFiles =
          await _messageProvider.uploadFiles([File(attachmentPath)], conversationId, addToState: false);
      if (uploadedFiles != null) {
        fileIds = uploadedFiles.map((f) => f.id).toList();
      }
    }

    // Add user message to the main chat history
    _messageProvider.addMessageLocally(text, appId: conversationId);

    String fullResponse = "";

    await _messageProvider.sendMessageStreamToServer(
      text,
      appId: conversationId,
      fileIds: fileIds,
      onChunk: (chunk) {
        if (chunk.type == MessageChunkType.data) {
          fullResponse += chunk.text;
          final aiResponse = {
            'text': fullResponse,
            'conversationId': conversationId,
            'messageId': chunk.messageId,
            'isFinal': false,
          };
          FloatingChatService.sendAIResponse(aiResponse);
        } else if (chunk.type == MessageChunkType.done) {
          final responseText = chunk.message?.text ?? fullResponse;
          final aiResponse = {
            'text': responseText,
            'conversationId': conversationId,
            'messageId': chunk.messageId,
            'isFinal': true,
          };
          FloatingChatService.sendAIResponse(aiResponse);
        } else if (chunk.type == MessageChunkType.error) {
          final aiResponse = {
            'text': chunk.text,
            'conversationId': conversationId,
            'messageId': chunk.messageId,
            'isFinal': true,
          };
          FloatingChatService.sendAIResponse(aiResponse);
        }
      },
    );
  }

  @override
  void dispose() {
    _messageSubscription?.cancel();
    super.dispose();
  }
}
