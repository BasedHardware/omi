import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';

abstract interface class CaptureExternalActions {
  bool? get isOutOfCredits;

  String? get topConversationId;

  Future<void> sendVoiceMessageStreamToServer(
    List<List<int>> data, {
    required VoidCallback onFirstChunkRecived,
    required BleAudioCodec codec,
    required bool playResponseAudio,
  });

  void addProcessingConversation(ServerConversation conversation);

  void removeProcessingConversation(String conversationId);

  void upsertConversation(ServerConversation conversation);

  bool hasConversation(String conversationId);

  Future<Person?> createPerson(String name);

  Future<void> refreshPeople();

  Future<void> markAsOutOfCreditsAndRefresh();

  Future<void> refreshSubscription();

  Future<void> fetchSubscription();
}

class NoopCaptureExternalActions implements CaptureExternalActions {
  const NoopCaptureExternalActions();

  @override
  bool? get isOutOfCredits => null;

  @override
  String? get topConversationId => null;

  @override
  Future<void> sendVoiceMessageStreamToServer(
    List<List<int>> data, {
    required VoidCallback onFirstChunkRecived,
    required BleAudioCodec codec,
    required bool playResponseAudio,
  }) async {}

  @override
  void addProcessingConversation(ServerConversation conversation) {}

  @override
  void removeProcessingConversation(String conversationId) {}

  @override
  void upsertConversation(ServerConversation conversation) {}

  @override
  bool hasConversation(String conversationId) => false;

  @override
  Future<Person?> createPerson(String name) async => null;

  @override
  Future<void> refreshPeople() async {}

  @override
  Future<void> markAsOutOfCreditsAndRefresh() async {}

  @override
  Future<void> refreshSubscription() async {}

  @override
  Future<void> fetchSubscription() async {}
}
