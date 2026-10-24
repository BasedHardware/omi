import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';

abstract interface class CaptureExternalActions {
  bool? get isOutOfCredits;

  String? get topConversationId;

  Future<void> sendVoiceMessageStreamToServer(
    List<List<int>> data, {
    required VoidCallback onFirstChunkRecived,
    required Future<void> Function() onNoSpeech,
    required BleAudioCodec codec,
    required bool playResponseAudio,
  });

  void addProcessingConversation(ServerConversation conversation);

  void removeProcessingConversation(String conversationId);

  void upsertConversation(ServerConversation conversation);

  bool hasConversation(String conversationId);

  /// Home should explain that the last recording was too short to keep.
  void showEmptyRecordingExplanation();

  /// Home should explain a discarded-only list.
  ///
  /// [DiscardedOnlyClaim.shown] is the first announcement.
  /// [DiscardedOnlyClaim.alreadyShown] means the Home line was already shown,
  /// and the capture should still emit analytics once.
  /// [DiscardedOnlyClaim.notDiscardedOnly] means there is nothing to explain.
  DiscardedOnlyClaim claimDiscardedOnlyExplanation();

  void clearEmptyRecordingExplanation();

  /// The person ended the live conversation (Wrap up, a pendant double-tap, Finish). The live
  /// episode closes and a fresh one starts counting from now (David 2026-10-23).
  void onLiveFinalized();

  Future<Person?> createPerson(String name);

  Future<bool> assignSpeaker(String conversationId, List<String> segmentIds, String personId, {int? speakerId});

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
    required Future<void> Function() onNoSpeech,
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
  void showEmptyRecordingExplanation() {}

  @override
  DiscardedOnlyClaim claimDiscardedOnlyExplanation() => DiscardedOnlyClaim.notDiscardedOnly;

  @override
  void clearEmptyRecordingExplanation() {}

  @override
  void onLiveFinalized() {}

  @override
  Future<Person?> createPerson(String name) async => null;

  @override
  Future<bool> assignSpeaker(String conversationId, List<String> segmentIds, String personId, {int? speakerId}) async =>
      false;

  @override
  Future<void> refreshPeople() async {}

  @override
  Future<void> markAsOutOfCreditsAndRefresh() async {}

  @override
  Future<void> refreshSubscription() async {}

  @override
  Future<void> fetchSubscription() async {}
}
