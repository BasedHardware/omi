import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

abstract class MessageEvent {
  final String eventType;

  MessageEvent({required this.eventType});

  factory MessageEvent.fromJson(Map<String, dynamic> json) {
    switch (json['type']) {
      case 'service_status':
        return MessageServiceStatusEvent.fromJson(json);
      case 'memory_processing_started':
        return ConversationProcessingStartedEvent.fromJson(json);
      case 'memory_created':
        return ConversationEvent.fromJson(json);
      case 'last_memory':
        return LastConversationEvent.fromJson(json);
      case 'translating':
        return TranslationEvent.fromJson(json);
      case 'photo_processing':
        return PhotoProcessingEvent.fromJson(json);
      case 'photo_described':
        return PhotoDescribedEvent.fromJson(json);
      case 'speaker_label_suggestion':
        return SpeakerLabelSuggestionEvent.fromJson(json);
      case 'onboarding_question':
        return OnboardingQuestionEvent.fromJson(json);
      case 'question_answered':
        return OnboardingQuestionAnsweredEvent.fromJson(json);
      case 'onboarding_complete':
        return OnboardingCompleteEvent.fromJson(json);
      case 'freemium_threshold_reached':
        return FreemiumThresholdReachedEvent.fromJson(json);
      default:
        // Return a generic event or throw an error if the type is unknown
        return UnknownEvent(eventType: json['type'] ?? 'unknown');
    }
  }
}

class UnknownEvent extends MessageEvent {
  UnknownEvent({required super.eventType});
}

class MessageServiceStatusEvent extends MessageEvent {
  final String status;
  final String? statusText;

  MessageServiceStatusEvent({required this.status, this.statusText}) : super(eventType: 'service_status');

  factory MessageServiceStatusEvent.fromJson(Map<String, dynamic> json) {
    return MessageServiceStatusEvent(
      status: json['status'],
      statusText: json['status_text'],
    );
  }
}

class ConversationProcessingStartedEvent extends MessageEvent {
  final ServerConversation memory;

  ConversationProcessingStartedEvent({required this.memory}) : super(eventType: 'memory_processing_started');

  factory ConversationProcessingStartedEvent.fromJson(Map<String, dynamic> json) {
    return ConversationProcessingStartedEvent(
      memory: ServerConversation.fromJson(json['memory']),
    );
  }
}

class ConversationEvent extends MessageEvent {
  final ServerConversation memory;
  final List messages;

  ConversationEvent({required this.memory, required this.messages}) : super(eventType: 'memory_created');

  factory ConversationEvent.fromJson(Map<String, dynamic> json) {
    return ConversationEvent(
      memory: ServerConversation.fromJson(json['memory']),
      messages: json['messages'] ?? [],
    );
  }
}

class LastConversationEvent extends MessageEvent {
  final String memoryId;

  LastConversationEvent({required this.memoryId}) : super(eventType: 'last_memory');

  factory LastConversationEvent.fromJson(Map<String, dynamic> json) {
    return LastConversationEvent(
      memoryId: json['memory_id'],
    );
  }
}

class TranslationEvent extends MessageEvent {
  final List<TranscriptSegment> segments;

  TranslationEvent({required this.segments}) : super(eventType: 'translating');

  factory TranslationEvent.fromJson(Map<String, dynamic> json) {
    return TranslationEvent(
      segments: (json['segments'] as List<dynamic>).map((s) => TranscriptSegment.fromJson(s)).toList(),
    );
  }
}

class PhotoProcessingEvent extends MessageEvent {
  final String tempId;
  final String photoId;

  PhotoProcessingEvent({required this.tempId, required this.photoId}) : super(eventType: 'photo_processing');

  factory PhotoProcessingEvent.fromJson(Map<String, dynamic> json) {
    return PhotoProcessingEvent(
      tempId: json['temp_id'],
      photoId: json['photo_id'],
    );
  }
}

class PhotoDescribedEvent extends MessageEvent {
  final String photoId;
  final String description;
  final bool discarded;

  PhotoDescribedEvent({
    required this.photoId,
    required this.description,
    this.discarded = false,
  }) : super(eventType: 'photo_described');

  factory PhotoDescribedEvent.fromJson(Map<String, dynamic> json) {
    return PhotoDescribedEvent(
      photoId: json['photo_id'],
      description: json['description'],
      discarded: json['discarded'] ?? false,
    );
  }
}

class SpeakerLabelSuggestionEvent extends MessageEvent {
  final int speakerId;
  final String personId;
  final String personName;
  final String segmentId;

  SpeakerLabelSuggestionEvent({
    required this.speakerId,
    required this.personId,
    required this.personName,
    required this.segmentId,
  }) : super(eventType: 'speaker_label_suggestion');

  factory SpeakerLabelSuggestionEvent.fromJson(Map<String, dynamic> json) {
    return SpeakerLabelSuggestionEvent(
      speakerId: json['speaker_id'],
      personId: json['person_id'],
      personName: json['person_name'],
      segmentId: json['segment_id'],
    );
  }

  static SpeakerLabelSuggestionEvent empty() {
    return SpeakerLabelSuggestionEvent(
      speakerId: -1,
      personId: '',
      personName: '',
      segmentId: '',
    );
  }
}

class OnboardingQuestionEvent extends MessageEvent {
  final String question;
  final int questionIndex;
  final int totalQuestions;

  OnboardingQuestionEvent({
    required this.question,
    required this.questionIndex,
    required this.totalQuestions,
  }) : super(eventType: 'onboarding_question');

  factory OnboardingQuestionEvent.fromJson(Map<String, dynamic> json) {
    return OnboardingQuestionEvent(
      question: json['question'] ?? '',
      questionIndex: json['question_index'] ?? 0,
      totalQuestions: json['total_questions'] ?? 0,
    );
  }
}

class OnboardingQuestionAnsweredEvent extends MessageEvent {
  final int questionIndex;
  final bool answered;

  OnboardingQuestionAnsweredEvent({
    required this.questionIndex,
    required this.answered,
  }) : super(eventType: 'question_answered');

  factory OnboardingQuestionAnsweredEvent.fromJson(Map<String, dynamic> json) {
    return OnboardingQuestionAnsweredEvent(
      questionIndex: json['question_index'] ?? 0,
      answered: json['answered'] ?? false,
    );
  }
}

class OnboardingCompleteEvent extends MessageEvent {
  final String? conversationId;
  final int memoriesCreated;
  final String? error;

  OnboardingCompleteEvent({
    this.conversationId,
    this.memoriesCreated = 0,
    this.error,
  }) : super(eventType: 'onboarding_complete');

  factory OnboardingCompleteEvent.fromJson(Map<String, dynamic> json) {
    return OnboardingCompleteEvent(
      conversationId: json['conversation_id'],
      memoriesCreated: json['memories_created'] ?? 0,
      error: json['error'],
    );
  }
}

/// Freemium action types sent by backend
enum FreemiumAction {
  /// User needs to setup on-device transcription to continue after credits run out
  setupOnDeviceStt,

  /// No action required - backend handles fallback automatically (future use)
  none;

  static FreemiumAction fromString(String? value) {
    switch (value) {
      case 'setup_on_device_stt':
        return FreemiumAction.setupOnDeviceStt;
      default:
        return FreemiumAction.none;
    }
  }
}

/// Freemium: Sent when user's credits are approaching the limit (e.g., 3 minutes remaining)
/// Includes action type to tell the app what the user needs to do (if anything)
class FreemiumThresholdReachedEvent extends MessageEvent {
  final int remainingSeconds;
  final FreemiumAction action;

  FreemiumThresholdReachedEvent({
    required this.remainingSeconds,
    required this.action,
  }) : super(eventType: 'freemium_threshold_reached');

  /// Whether user action is required
  bool get requiresUserAction => action == FreemiumAction.setupOnDeviceStt;

  factory FreemiumThresholdReachedEvent.fromJson(Map<String, dynamic> json) {
    return FreemiumThresholdReachedEvent(
      remainingSeconds: json['remaining_seconds'] ?? 0,
      action: FreemiumAction.fromString(json['action']),
    );
  }
}
