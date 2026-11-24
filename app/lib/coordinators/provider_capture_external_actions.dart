import 'dart:async';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/models/voice_question_result.dart';
import 'package:flutter/foundation.dart';
import 'package:omi/backend/http/api/recording_speakers.dart';

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
    this.conversationsV3,
  });

  final ConversationProvider conversationProvider;
  final MessageProvider messageProvider;
  final PeopleProvider peopleProvider;
  final UsageProvider usageProvider;
  final EpisodeProvider? episodeProvider;
  final ConversationsV3Provider? conversationsV3;

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
      identical(other.episodeProvider, episodeProvider) &&
      identical(other.conversationsV3, conversationsV3);

  @override
  int get hashCode => Object.hash(
        identityHashCode(conversationProvider),
        identityHashCode(messageProvider),
        identityHashCode(peopleProvider),
        identityHashCode(usageProvider),
        identityHashCode(episodeProvider),
        identityHashCode(conversationsV3),
      );

  @override
  bool? get isOutOfCredits => usageProvider.isOutOfCredits;

  @override
  String? get topConversationId {
    final conversations = conversationProvider.conversations;
    return conversations.isEmpty ? null : conversations.first.id;
  }

  @override
  Future<VoiceQuestionResult> sendVoiceMessageStreamToServer(
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
  bool get v3FinishFeedbackEnabled => conversationsV3?.finishFeedbackEnabled ?? false;

  @override
  void onManualFinishStarted(
    ServerConversation placeholder,
    String? recordingId, {
    String? liveConversationId,
    String? captureId,
  }) =>
      conversationsV3?.startManualFinish(placeholder, recordingId,
          liveConversationId: liveConversationId, captureId: captureId);

  @override
  void onManualFinishSettled(
    ServerConversation placeholder,
    InProgressProcessOutcome? outcome, {
    required bool showFailure,
  }) {
    final v3 = conversationsV3;
    final result = outcome?.response?.conversation;
    final alreadyClosed = outcome?.absence == ProcessAbsence.notFound;
    if (v3 == null || !v3.settleManualFinish(placeholder, result, alreadyClosed: alreadyClosed)) return;
    if (showFailure && !alreadyClosed) {
      final l10n = globalNavigatorKey.currentContext?.l10n;
      if (l10n != null) {
        if (outcome?.absence == ProcessAbsence.emptyBody || result?.discarded == true) {
          AppSnackbar.showSnackbar(l10n.discardedOnlyRecording);
        } else if (result == null) {
          AppSnackbar.showSnackbarError(l10n.finishFailed);
        } else if (result.status == ConversationStatus.in_progress) {
          AppSnackbar.showSnackbar(l10n.finishAudioNotReceived);
        }
      }
    }
    unawaited(v3.refreshAfterManualFinish().catchError((Object _) {}));
    // A 404 leaves the pending row on Home. Reload once, with transient filters already cleared.
    final refresh = alreadyClosed && !conversationProvider.showsPendingFinishOnHome
        ? conversationProvider.resetToDefaultHome()
        : conversationProvider.forceRefreshConversations();
    unawaited(refresh.catchError((Object _) {}));
  }

  @override
  Future<Person?> createPerson(String name) {
    return peopleProvider.createPersonProvider(name);
  }

  @override
  int lastSpeakerAppliedCount = 0;

  @override
  bool lastSpeakerCoverageComplete = false;

  @override
  Future<bool> assignSpeaker(String conversationId, List<String> segmentIds, String personId,
      {int? speakerId, (String, String)? voice}) async {
    final result = await assignRecordingSpeakers(
        conversationId,
        [
          {
            'conversation_id': conversationId,
            'segment_ids': segmentIds,
            if (speakerId != null) 'speaker_id': speakerId,
            if (voice != null) 'voice': {'speaker_id_scope': voice.$1, 'stream_speaker': voice.$2}
          },
        ],
        personId: personId,
        wholeRecording: speakerId != null);
    if (result is ApiFailure<int> && result.problem.statusCode == 413) throw const RecordingSpeakerLimitException();
    if (result is ApiFailure<int> && result.problem.statusCode == 409) throw const StaleSpeakerException();
    lastSpeakerCoverageComplete = result is ApiSuccess<int> && !result.truncated;
    lastSpeakerAppliedCount = result is ApiSuccess<int> ? result.data : 0;
    return result is ApiSuccess<int>;
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
