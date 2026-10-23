import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/conversations.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';

class ProviderCaptureExternalActions implements CaptureExternalActions {
  ProviderCaptureExternalActions({
    required this.conversationProvider,
    required this.messageProvider,
    required this.peopleProvider,
    required this.usageProvider,
    this.episodeProvider,
  });

  final ConversationProvider conversationProvider;
  final MessageProvider messageProvider;
  final PeopleProvider peopleProvider;
  final UsageProvider usageProvider;
  final EpisodeProvider? episodeProvider;

  /// The proxy provider rebuilds this adapter on every upstream notify. Two
  /// adapters over the same provider instances behave identically, so the
  /// capture controller can skip re-installing (and re-notifying) it.
  @override
  bool operator ==(Object other) =>
      other is ProviderCaptureExternalActions &&
      identical(other.conversationProvider, conversationProvider) &&
      identical(other.messageProvider, messageProvider) &&
      identical(other.peopleProvider, peopleProvider) &&
      identical(other.usageProvider, usageProvider) &&
      identical(other.episodeProvider, episodeProvider);

  @override
  int get hashCode => Object.hash(identityHashCode(conversationProvider), identityHashCode(messageProvider),
      identityHashCode(peopleProvider), identityHashCode(usageProvider), identityHashCode(episodeProvider));

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
    required Future<void> Function() onNoSpeech,
    required BleAudioCodec codec,
    required bool playResponseAudio,
  }) {
    return messageProvider.sendVoiceMessageStreamToServer(
      data,
      onFirstChunkRecived: onFirstChunkRecived,
      onNoSpeech: onNoSpeech,
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
  void showEmptyRecordingExplanation() => conversationProvider.showEmptyRecordingExplanation();

  @override
  DiscardedOnlyClaim claimDiscardedOnlyExplanation() => conversationProvider.claimDiscardedOnlyExplanation();

  @override
  void clearEmptyRecordingExplanation() => conversationProvider.clearEmptyRecordingExplanation();

  @override
  void onLiveFinalized() => episodeProvider?.onLiveFinalized();

  @override
  Future<Person?> createPerson(String name) {
    return peopleProvider.createPersonProvider(name);
  }

  @override
  Future<bool> assignSpeaker(String conversationId, List<String> segmentIds, String personId, {int? speakerId}) =>
      assignBulkConversationTranscriptSegments(conversationId, segmentIds,
          isUser: personId == 'user', personId: personId == 'user' ? null : personId, speakerId: speakerId);

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
