import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';

class ProviderCaptureExternalActions implements CaptureExternalActions {
  ProviderCaptureExternalActions({
    required this.conversationProvider,
    required this.messageProvider,
    required this.peopleProvider,
    required this.usageProvider,
  });

  final ConversationProvider conversationProvider;
  final MessageProvider messageProvider;
  final PeopleProvider peopleProvider;
  final UsageProvider usageProvider;

  @override
  bool? get isOutOfCredits => usageProvider.isOutOfCredits;

  @override
  String? get topConversationId {
    final conversations = conversationProvider.conversations;
    return conversations.isEmpty ? null : conversations.first.id;
  }

  @override
  Future<void> sendVoiceMessageStreamToServer(
    List<List<int>> data, {
    required VoidCallback onFirstChunkRecived,
    required BleAudioCodec codec,
    required bool playResponseAudio,
  }) {
    return messageProvider.sendVoiceMessageStreamToServer(
      data,
      onFirstChunkRecived: onFirstChunkRecived,
      codec: codec,
      playResponseAudio: playResponseAudio,
    );
  }

  @override
  void addProcessingConversation(ServerConversation conversation) {
    conversationProvider.addProcessingConversation(conversation);
  }

  @override
  void removeProcessingConversation(String conversationId) {
    conversationProvider.removeProcessingConversation(conversationId);
  }

  @override
  void upsertConversation(ServerConversation conversation) {
    conversationProvider.upsertConversation(conversation);
  }

  @override
  bool hasConversation(String conversationId) {
    return conversationProvider.conversations.any((conversation) => conversation.id == conversationId);
  }

  @override
  Future<Person?> createPerson(String name) {
    return peopleProvider.createPersonProvider(name);
  }

  @override
  Future<void> refreshPeople() {
    return peopleProvider.setPeople();
  }

  @override
  Future<void> markAsOutOfCreditsAndRefresh() {
    return usageProvider.markAsOutOfCreditsAndRefresh();
  }

  @override
  Future<void> refreshSubscription() {
    return usageProvider.refreshSubscription();
  }

  @override
  Future<void> fetchSubscription() {
    return usageProvider.fetchSubscription();
  }
}
