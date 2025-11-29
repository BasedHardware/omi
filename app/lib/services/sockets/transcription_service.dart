import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/utils/debug_log_manager.dart';

export 'package:omi/services/sockets/audio_transcoder.dart';
export 'package:omi/services/sockets/composite_transcription_socket.dart';
export 'package:omi/services/sockets/pure_polling.dart';
export 'package:omi/services/sockets/stt_response_schema.dart';
export 'package:omi/services/sockets/stt_result.dart';
export 'package:omi/services/sockets/transcription_polling_service.dart';

abstract interface class ITransctiptSegmentSocketServiceListener {
  void onMessageEventReceived(MessageEvent event);

  void onSegmentReceived(List<TranscriptSegment> segments);

  void onError(Object err);

  void onConnected();

  void onClosed([int? closeCode]);
}

class SpeechProfileTranscriptSegmentSocketService extends TranscriptSegmentSocketService {
  SpeechProfileTranscriptSegmentSocketService.create(super.sampleRate, super.codec, super.language,
      {super.source, super.customSttMode})
      : super.create(includeSpeechProfile: false);
}

class ConversationTranscriptSegmentSocketService extends TranscriptSegmentSocketService {
  ConversationTranscriptSegmentSocketService.create(super.sampleRate, super.codec, super.language,
      {super.source, super.customSttMode})
      : super.create(includeSpeechProfile: true);
}

class CustomSttTranscriptSegmentSocketService extends TranscriptSegmentSocketService {
  CustomSttTranscriptSegmentSocketService.create(super.sampleRate, super.codec, super.language, {super.source})
      : super.create(includeSpeechProfile: true, customSttMode: true);
}

enum SocketServiceState {
  connected,
  disconnected,
}

class TranscriptSegmentSocketService implements IPureSocketListener {
  late IPureSocket _socket;
  final Map<Object, ITransctiptSegmentSocketServiceListener> _listeners = {};

  /// Access to the underlying socket (for composite service creation)
  IPureSocket get socket => _socket;

  SocketServiceState get state =>
      _socket.status == PureSocketStatus.connected ? SocketServiceState.connected : SocketServiceState.disconnected;

  int sampleRate;
  BleAudioCodec codec;
  String language;
  bool includeSpeechProfile;
  String? source;
  bool customSttMode;

  TranscriptSegmentSocketService.create(
    this.sampleRate,
    this.codec,
    this.language, {
    this.includeSpeechProfile = false,
    this.source,
    this.customSttMode = false,
  }) {
    var params = '?language=$language&sample_rate=$sampleRate&codec=$codec&uid=${SharedPreferencesUtil().uid}'
        '&include_speech_profile=$includeSpeechProfile&stt_service=${SharedPreferencesUtil().transcriptionModel}'
        '&conversation_timeout=${SharedPreferencesUtil().conversationSilenceDuration}';

    if (source != null && source!.isNotEmpty) {
      params += '&source=${Uri.encodeComponent(source!)}';
    }

    if (customSttMode) {
      params += '&custom_stt=enabled';
    }

    String url =
        Env.apiBaseUrl!.replaceFirst('https://', 'wss://').replaceFirst('http://', 'ws://') + 'v4/listen$params';

    _socket = PureSocket(url);
    _socket.setListener(this);
  }

  TranscriptSegmentSocketService.withSocket(
    this.sampleRate,
    this.codec,
    this.language,
    IPureSocket socket, {
    this.includeSpeechProfile = false,
    this.source,
    this.customSttMode = false,
  }) {
    _socket = socket;
    _socket.setListener(this);
  }

  void subscribe(Object context, ITransctiptSegmentSocketServiceListener listener) {
    _listeners.remove(context.hashCode);
    _listeners.putIfAbsent(context.hashCode, () => listener);
  }

  void unsubscribe(Object context) {
    _listeners.remove(context.hashCode);
  }

  Future start() async {
    bool ok = await _socket.connect();
    if (!ok) {
      debugPrint("Can not connect to websocket");
      await DebugLogManager.logWarning('transcription_socket_connect_failed', {
        'url': Env.apiBaseUrl?.replaceAll('https', 'wss') ?? 'null',
        'sample_rate': sampleRate,
        'codec': codec.toString(),
        'language': language,
      });
    }
  }

  Future stop({String? reason}) async {
    await _socket.stop();
    _listeners.clear();

    if (reason != null) {
      debugPrint(reason);
      await DebugLogManager.logInfo('transcription_socket_stopped', {'reason': reason});
    }
  }

  Future send(dynamic message) async {
    _socket.send(message);
    return;
  }

  @override
  void onClosed([int? closeCode]) {
    _listeners.forEach((k, v) {
      v.onClosed(closeCode);
    });
    DebugLogManager.logEvent('transcription_socket_closed', {
      'close_code': closeCode ?? -1,
    });
  }

  @override
  void onError(Object err, StackTrace trace) {
    _listeners.forEach((k, v) {
      v.onError(err);
    });
    DebugLogManager.logError(err, trace, 'transcription_socket_error');
  }

  @override
  void onMessage(event) {
    // Decode json
    dynamic jsonEvent;
    try {
      jsonEvent = jsonDecode(event);
    } on FormatException catch (e) {
      debugPrint(e.toString());
      DebugLogManager.logWarning('transcription_socket_parse_error', {'error': e.toString()});
    }
    if (jsonEvent == null) {
      debugPrint("Can not decode message event json $event");
      return;
    }

    // Transcript segments
    if (jsonEvent is List) {
      var segments = jsonEvent;
      if (segments.isEmpty) {
        return;
      }
      _listeners.forEach((k, v) {
        v.onSegmentReceived(segments.map((e) => TranscriptSegment.fromJson(e)).toList());
      });
      return;
    }

    // Message event
    if (jsonEvent.containsKey("type")) {
      var event = MessageEvent.fromJson(jsonEvent);
      _listeners.forEach((k, v) {
        v.onMessageEventReceived(event);
      });
      return;
    }

    debugPrint(event.toString());
    DebugLogManager.logInfo('transcription_socket_unhandled_message: ${event.toString()}');
  }

  @override
  void onInternetConnectionFailed() {
    debugPrint("onInternetConnectionFailed");

    // Send notification
    NotificationService.instance.clearNotification(3);
    NotificationService.instance.createNotification(
      notificationId: 3,
      title: 'Internet Connection Lost',
      body: 'Your device is offline. Transcription is paused until connection is restored.',
    );
    DebugLogManager.logEvent('internet_connection_lost', {});
  }

  @override
  void onMaxRetriesReach() {
    debugPrint("onMaxRetriesReach");

    // Send notification
    NotificationService.instance.clearNotification(2);
    NotificationService.instance.createNotification(
      notificationId: 2,
      title: 'Connection Issue 🚨',
      body: 'Unable to connect to the transcript service.'
          ' Please restart the app or contact support if the problem persists.',
    );
    DebugLogManager.logEvent('transcription_socket_max_retries', {});
  }

  @override
  void onConnected() {
    _listeners.forEach((k, v) {
      v.onConnected();
    });
    DebugLogManager.logEvent('transcription_socket_connected', {
      'sample_rate': sampleRate,
      'codec': codec.toString(),
      'language': language,
      'include_speech_profile': includeSpeechProfile,
    });
  }
}

class TranscriptSocketServiceFactory {
  TranscriptSocketServiceFactory._();

  static TranscriptSegmentSocketService createDefault(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    bool includeSpeechProfile = true,
    String? source,
  }) {
    return ConversationTranscriptSegmentSocketService.create(
      sampleRate,
      codec,
      language,
      source: source,
    );
  }

  static TranscriptSegmentSocketService createSpeechProfile(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    String? source,
  }) {
    return SpeechProfileTranscriptSegmentSocketService.create(
      sampleRate,
      codec,
      language,
      source: source,
    );
  }

  static TranscriptSegmentSocketService createOpenAI(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    String model = 'whisper-1',
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) {
    return _createPollingService(
      sampleRate,
      codec,
      language,
      _createOpenAISocket(sampleRate, codec, language,
          apiKey: apiKey, model: model, bufferDuration: bufferDuration, transcoder: transcoder),
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static TranscriptSegmentSocketService createDeepgram(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) {
    return _createPollingService(
      sampleRate,
      codec,
      language,
      _createDeepgramSocket(sampleRate, codec, language,
          apiKey: apiKey, bufferDuration: bufferDuration, transcoder: transcoder),
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static TranscriptSegmentSocketService createFalAI(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) {
    return _createPollingService(
      sampleRate,
      codec,
      language,
      _createFalAISocket(sampleRate, codec, language,
          apiKey: apiKey, bufferDuration: bufferDuration, transcoder: transcoder),
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static TranscriptSegmentSocketService createGemini(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    String model = 'gemini-2.0-flash',
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) {
    return _createPollingService(
      sampleRate,
      codec,
      language,
      _createGeminiSocket(sampleRate, codec, language,
          apiKey: apiKey, model: model, bufferDuration: bufferDuration, transcoder: transcoder),
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static TranscriptSegmentSocketService createSchemaBased(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiUrl,
    required SttResponseSchema schema,
    Map<String, String> headers = const {},
    Map<String, String> fields = const {},
    String audioFieldName = 'audio',
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) {
    return _createPollingService(
      sampleRate,
      codec,
      language,
      _createSchemaBasedSocket(
        sampleRate,
        codec,
        apiUrl: apiUrl,
        schema: schema,
        headers: headers,
        fields: fields,
        audioFieldName: audioFieldName,
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      ),
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static TranscriptSegmentSocketService createCompositeWithOpenAI(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String openAiApiKey,
    String openAiModel = 'whisper-1',
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) {
    final primarySocket = _createOpenAISocket(
      sampleRate,
      codec,
      language,
      apiKey: openAiApiKey,
      model: openAiModel,
      bufferDuration: bufferDuration,
      transcoder: transcoder,
    );
    return _createCompositeService(
      sampleRate,
      codec,
      language,
      primarySocket: primarySocket,
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static TranscriptSegmentSocketService createCompositeWithDeepgram(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String deepgramApiKey,
    bool includeSpeechProfile = false,
    String? source,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) {
    final primarySocket = _createDeepgramSocket(
      sampleRate,
      codec,
      language,
      apiKey: deepgramApiKey,
      bufferDuration: bufferDuration,
      transcoder: transcoder,
    );
    return _createCompositeService(
      sampleRate,
      codec,
      language,
      primarySocket: primarySocket,
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static TranscriptSegmentSocketService createCompositeCustom(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required IPureSocket primarySocket,
    required IPureSocket secondarySocket,
    bool includeSpeechProfile = false,
    String? source,
    String? suggestedTranscriptType = 'suggested_transcript',
  }) {
    final compositeSocket = CompositeTranscriptionSocket(
      primarySocket: primarySocket,
      secondarySocket: secondarySocket,
      suggestedTranscriptType: suggestedTranscriptType,
    );
    return TranscriptSegmentSocketService.withSocket(
      sampleRate,
      codec,
      language,
      compositeSocket,
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static TranscriptSegmentSocketService createWithSocket(
    int sampleRate,
    BleAudioCodec codec,
    String language,
    IPureSocket socket, {
    bool includeSpeechProfile = false,
    String? source,
  }) {
    return TranscriptSegmentSocketService.withSocket(
      sampleRate,
      codec,
      language,
      socket,
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static TranscriptSegmentSocketService _createCompositeService(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required IPureSocket primarySocket,
    bool includeSpeechProfile = false,
    String? source,
  }) {
    final secondaryService = CustomSttTranscriptSegmentSocketService.create(
      sampleRate,
      codec,
      language,
      source: source,
    );
    final compositeSocket = CompositeTranscriptionSocket(
      primarySocket: primarySocket,
      secondarySocket: secondaryService.socket,
    );
    return TranscriptSegmentSocketService.withSocket(
      sampleRate,
      codec,
      language,
      compositeSocket,
      includeSpeechProfile: includeSpeechProfile,
      source: source,
      customSttMode: true,
    );
  }

  static TranscriptSegmentSocketService _createPollingService(
    int sampleRate,
    BleAudioCodec codec,
    String language,
    PurePollingSocket socket, {
    bool includeSpeechProfile = false,
    String? source,
  }) {
    return TranscriptSegmentSocketService.withSocket(
      sampleRate,
      codec,
      language,
      socket,
      includeSpeechProfile: includeSpeechProfile,
      source: source,
    );
  }

  static PurePollingSocket _createPollingSocket(
    int sampleRate,
    BleAudioCodec codec,
    ISttProvider provider, {
    required String serviceId,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) {
    return PurePollingSocket(
      config: AudioPollingConfig(
        bufferDuration: bufferDuration,
        minBufferSizeBytes: sampleRate * 2,
        serviceId: serviceId,
        transcoder: transcoder ?? AudioTranscoderFactory.createToWav(sourceCodec: codec, sampleRate: sampleRate),
      ),
      sttProvider: provider,
    );
  }

  static PurePollingSocket _createOpenAISocket(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    String model = 'whisper-1',
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createPollingSocket(
        sampleRate,
        codec,
        SchemaBasedSttProvider.openAI(apiKey: apiKey, model: model, language: language),
        serviceId: 'openai-whisper',
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      );

  static PurePollingSocket _createDeepgramSocket(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createPollingSocket(
        sampleRate,
        codec,
        SchemaBasedSttProvider.deepgram(apiKey: apiKey, language: language),
        serviceId: 'deepgram',
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      );

  static PurePollingSocket _createFalAISocket(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createPollingSocket(
        sampleRate,
        codec,
        SchemaBasedSttProvider.falAI(apiKey: apiKey, language: language),
        serviceId: 'fal-ai-whisper',
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      );

  static PurePollingSocket _createGeminiSocket(
    int sampleRate,
    BleAudioCodec codec,
    String language, {
    required String apiKey,
    String model = 'gemini-2.0-flash',
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createPollingSocket(
        sampleRate,
        codec,
        SchemaBasedSttProvider.gemini(apiKey: apiKey, model: model, language: language),
        serviceId: 'gemini',
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      );

  static PurePollingSocket _createSchemaBasedSocket(
    int sampleRate,
    BleAudioCodec codec, {
    required String apiUrl,
    required SttResponseSchema schema,
    Map<String, String> headers = const {},
    Map<String, String> fields = const {},
    String audioFieldName = 'audio',
    Duration bufferDuration = const Duration(seconds: 5),
    IAudioTranscoder? transcoder,
  }) =>
      _createPollingSocket(
        sampleRate,
        codec,
        SchemaBasedSttProvider(
          apiUrl: apiUrl,
          schema: schema,
          defaultHeaders: headers,
          defaultFields: fields,
          audioFieldName: audioFieldName,
        ),
        serviceId: apiUrl,
        bufferDuration: bufferDuration,
        transcoder: transcoder,
      );
}
