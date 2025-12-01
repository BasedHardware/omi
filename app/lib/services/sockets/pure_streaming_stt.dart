import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/models/stt_result.dart';
import 'package:omi/utils/audio/audio_transcoder.dart';

/// Configuration for streaming STT WebSocket connections
class StreamingSttConfig {
  final String wsUrl;
  final Map<String, String> headers;
  final SttResponseSchema responseSchema;
  final IAudioTranscoder? transcoder;
  final String serviceId;
  final int minBytesBeforeSend;
  final bool sendKeepAlive;
  final Duration keepAliveInterval;

  const StreamingSttConfig({
    required this.wsUrl,
    this.headers = const {},
    required this.responseSchema,
    this.transcoder,
    this.serviceId = 'streaming-stt',
    this.minBytesBeforeSend = 0,
    this.sendKeepAlive = false,
    this.keepAliveInterval = const Duration(seconds: 10),
  });

  /// Factory for Deepgram streaming WebSocket
  /// Matches backend params from backend/utils/stt/streaming.py
  factory StreamingSttConfig.deepgramLive({
    required String apiKey,
    String model = 'nova-3',
    String language = 'multi',
    bool smartFormat = true,
    bool interimResults = false, // Must be false to avoid duplicates
    bool punctuate = true,
    bool diarize = true,
    bool noDelay = true,
    int endpointing = 300,
    bool profanityFilter = false,
    bool fillerWords = false,
    int sampleRate = 16000,
    String encoding = 'linear16',
    int channels = 1,
    IAudioTranscoder? transcoder,
  }) {
    final params = {
      'model': model,
      'language': language,
      'smart_format': smartFormat.toString(),
      'interim_results': interimResults.toString(),
      'punctuate': punctuate.toString(),
      'diarize': diarize.toString(),
      'no_delay': noDelay.toString(),
      'endpointing': endpointing.toString(),
      'profanity_filter': profanityFilter.toString(),
      'filler_words': fillerWords.toString(),
      'encoding': encoding,
      'sample_rate': sampleRate.toString(),
      'channels': channels.toString(),
    };
    final queryString = params.entries.map((e) => '${e.key}=${e.value}').join('&');

    return StreamingSttConfig(
      wsUrl: 'wss://api.deepgram.com/v1/listen?$queryString',
      headers: {'Authorization': 'Token $apiKey'},
      responseSchema: SttResponseSchema.deepgramLive,
      transcoder: transcoder,
      serviceId: 'deepgram-streaming',
      sendKeepAlive: true,
      keepAliveInterval: const Duration(seconds: 8),
    );
  }

  /// Factory for Gemini Live streaming WebSocket
  factory StreamingSttConfig.geminiLive({
    required String apiKey,
    String model = 'gemini-2.0-flash-exp',
    String language = 'en',
    int sampleRate = 16000,
    IAudioTranscoder? transcoder,
  }) {
    return StreamingSttConfig(
      wsUrl: 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=$apiKey',
      headers: {},
      responseSchema: SttResponseSchema.geminiLive,
      transcoder: transcoder,
      serviceId: 'gemini-streaming',
      sendKeepAlive: false,
      minBytesBeforeSend: sampleRate * 2,
    );
  }

  /// Factory for generic schema-based streaming WebSocket
  factory StreamingSttConfig.schemaBased({
    required String wsUrl,
    required SttResponseSchema schema,
    Map<String, String> headers = const {},
    IAudioTranscoder? transcoder,
    String serviceId = 'custom-streaming',
    int minBytesBeforeSend = 0,
    bool sendKeepAlive = false,
    Duration keepAliveInterval = const Duration(seconds: 10),
  }) {
    return StreamingSttConfig(
      wsUrl: wsUrl,
      headers: headers,
      responseSchema: schema,
      transcoder: transcoder,
      serviceId: serviceId,
      minBytesBeforeSend: minBytesBeforeSend,
      sendKeepAlive: sendKeepAlive,
      keepAliveInterval: keepAliveInterval,
    );
  }
}

/// Gemini Live streaming socket with setup message and base64 audio encoding
class GeminiStreamingSttSocket implements IPureSocket {
  StreamSubscription<bool>? _connectionStateListener;
  bool _isConnected = ConnectivityService().isConnected;
  Timer? _internetLostDelayTimer;

  WebSocketChannel? _channel;

  final String apiKey;
  final String model;
  final String language;
  final int sampleRate;
  final IAudioTranscoder? transcoder;

  PureSocketStatus _status = PureSocketStatus.notConnected;
  @override
  PureSocketStatus get status => _status;

  IPureSocketListener? _listener;

  int _retries = 0;
  double _audioOffsetSeconds = 0;
  bool _setupSent = false;

  final List<Uint8List> _frameBuffer = [];
  int _bufferedBytes = 0;
  static const int _minBytesBeforeSend = 16000;

  GeminiStreamingSttSocket({
    required this.apiKey,
    this.model = 'gemini-2.0-flash-exp',
    this.language = 'en',
    this.sampleRate = 16000,
    this.transcoder,
  }) {
    _connectionStateListener = ConnectivityService().onConnectionChange.listen((bool isConnected) {
      onConnectionStateChanged(isConnected);
    });
  }

  @override
  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  String get _wsUrl =>
      'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=$apiKey';

  @override
  Future<bool> connect() async {
    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return false;
    }

    debugPrint("[GeminiStreaming] Connecting...");
    _status = PureSocketStatus.connecting;

    try {
      _channel = IOWebSocketChannel.connect(
        _wsUrl,
        pingInterval: const Duration(seconds: 20),
        connectTimeout: const Duration(seconds: 15),
      );

      await _channel!.ready;

      _status = PureSocketStatus.connected;
      _retries = 0;
      _setupSent = false;

      _channel!.stream.listen(
        _handleMessage,
        onError: (err, trace) => onError(err, trace),
        onDone: () => onClosed(_channel?.closeCode),
        cancelOnError: true,
      );

      await _sendSetupMessage();

      onConnected();
      return true;
    } on TimeoutException catch (e) {
      debugPrint("[GeminiStreaming] Connection timeout: $e");
      _status = PureSocketStatus.notConnected;
      return false;
    } on SocketException catch (e) {
      debugPrint("[GeminiStreaming] Socket error: $e");
      _status = PureSocketStatus.notConnected;
      return false;
    } on WebSocketChannelException catch (e) {
      debugPrint("[GeminiStreaming] WebSocket error: $e");
      _status = PureSocketStatus.notConnected;
      return false;
    } catch (e) {
      debugPrint("[GeminiStreaming] Connection error: $e");
      _status = PureSocketStatus.notConnected;
      return false;
    }
  }

  Future<void> _sendSetupMessage() async {
    if (_setupSent) return;

    final setupMessage = {
      'setup': {
        'model': 'models/$model',
        'generationConfig': {
          'responseModalities': ['TEXT'],
        },
        'systemInstruction': {
          'parts': [
            {
              'text': 'You are a speech-to-text transcription service. '
                  'Listen to the audio and transcribe it accurately in $language. '
                  'Return only the transcription text, no explanations or formatting. '
                  'If you cannot understand the audio, return an empty string.',
            }
          ]
        }
      }
    };

    try {
      _channel!.sink.add(jsonEncode(setupMessage));
      _setupSent = true;
      debugPrint("[GeminiStreaming] Setup message sent");
    } catch (e) {
      debugPrint("[GeminiStreaming] Failed to send setup: $e");
    }
  }

  void _handleMessage(dynamic message) {
    if (message is! String) {
      debugPrint("[GeminiStreaming] Non-string message received");
      return;
    }

    try {
      final json = jsonDecode(message);

      if (json.containsKey('setupComplete')) {
        debugPrint("[GeminiStreaming] Setup complete");
        return;
      }

      if (json.containsKey('toolCall')) {
        return;
      }

      String? text;
      if (json.containsKey('serverContent')) {
        final serverContent = json['serverContent'];
        if (serverContent != null && serverContent.containsKey('modelTurn')) {
          final modelTurn = serverContent['modelTurn'];
          if (modelTurn != null && modelTurn.containsKey('parts')) {
            final parts = modelTurn['parts'] as List?;
            if (parts != null && parts.isNotEmpty) {
              text = parts[0]['text'] as String?;
            }
          }
        }
      }

      if (text != null && text.trim().isNotEmpty) {
        final segment = {
          'text': text.trim(),
          'speaker': 'SPEAKER_0',
          'speaker_id': 0,
          'is_user': false,
          'start': _audioOffsetSeconds,
          'end': _audioOffsetSeconds + 3.0,
          'person_id': null,
        };
        _audioOffsetSeconds += 3.0;

        onMessage(jsonEncode([segment]));
      }
    } catch (e, trace) {
      debugPrint("[GeminiStreaming] Parse error: $e");
      debugPrintStack(stackTrace: trace);
    }
  }

  @override
  void send(dynamic message) {
    if (_status != PureSocketStatus.connected || _channel == null || !_setupSent) {
      return;
    }

    Uint8List audioData;
    if (message is Uint8List) {
      audioData = message;
    } else if (message is List<int>) {
      audioData = Uint8List.fromList(message);
    } else {
      debugPrint("[GeminiStreaming] Unsupported message type: ${message.runtimeType}");
      return;
    }

    _frameBuffer.add(audioData);
    _bufferedBytes += audioData.length;

    if (_bufferedBytes < _minBytesBeforeSend) {
      return;
    }

    final combined = Uint8List(_bufferedBytes);
    int offset = 0;
    for (final frame in _frameBuffer) {
      combined.setRange(offset, offset + frame.length, frame);
      offset += frame.length;
    }
    _frameBuffer.clear();
    _bufferedBytes = 0;

    Uint8List pcmData = combined;
    if (transcoder != null) {
      try {
        pcmData = transcoder!.transcodeFrames([combined]);
      } catch (e) {
        debugPrint("[GeminiStreaming] Transcode error: $e");
        return;
      }
    }

    final realtimeInput = {
      'realtimeInput': {
        'mediaChunks': [
          {
            'mimeType': 'audio/pcm;rate=$sampleRate',
            'data': base64Encode(pcmData),
          }
        ]
      }
    };

    try {
      _channel!.sink.add(jsonEncode(realtimeInput));
    } catch (e) {
      debugPrint("[GeminiStreaming] Send error: $e");
    }
  }

  @override
  Future disconnect() async {
    if (_bufferedBytes > 0 && _status == PureSocketStatus.connected) {
      final combined = Uint8List(_bufferedBytes);
      int offset = 0;
      for (final frame in _frameBuffer) {
        combined.setRange(offset, offset + frame.length, frame);
        offset += frame.length;
      }
      _frameBuffer.clear();
      _bufferedBytes = 0;

      Uint8List pcmData = combined;
      if (transcoder != null) {
        try {
          pcmData = transcoder!.transcodeFrames([combined]);
        } catch (_) {}
      }

      final realtimeInput = {
        'realtimeInput': {
          'mediaChunks': [
            {
              'mimeType': 'audio/pcm;rate=$sampleRate',
              'data': base64Encode(pcmData),
            }
          ]
        }
      };

      try {
        _channel!.sink.add(jsonEncode(realtimeInput));
      } catch (_) {}
    }

    await Future.delayed(const Duration(milliseconds: 500));

    _channel?.sink.close();
    _status = PureSocketStatus.disconnected;
    debugPrint("[GeminiStreaming] Disconnected");
    onClosed();
  }

  Future _cleanUp() async {
    _internetLostDelayTimer?.cancel();
    _connectionStateListener?.cancel();
    _frameBuffer.clear();
    _bufferedBytes = 0;
    _audioOffsetSeconds = 0;
    _setupSent = false;
  }

  @override
  Future stop() async {
    await disconnect();
    await _cleanUp();
  }

  @override
  void onConnected() {
    debugPrint("[GeminiStreaming] Connected");
    _listener?.onConnected();
  }

  @override
  void onMessage(dynamic message) {
    _listener?.onMessage(message);
  }

  @override
  void onClosed([int? closeCode]) {
    _status = PureSocketStatus.disconnected;
    debugPrint("[GeminiStreaming] Closed with code: $closeCode");
    _listener?.onClosed(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    debugPrint("[GeminiStreaming] Error: $err");
    _listener?.onError(err, trace);
  }

  void _reconnect() async {
    debugPrint("[GeminiStreaming] Reconnecting...${_retries + 1}...");
    const int initialBackoffTimeMs = 1000;
    const double multiplier = 1.5;
    const int maxRetries = 8;

    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return;
    }

    await _cleanUp();

    var ok = await connect();
    if (ok) return;

    int waitInMilliseconds = pow(multiplier, _retries).toInt() * initialBackoffTimeMs;
    await Future.delayed(Duration(milliseconds: waitInMilliseconds));
    _retries++;
    if (_retries > maxRetries) {
      debugPrint("[GeminiStreaming] Max retries reached");
      _listener?.onMaxRetriesReach();
      return;
    }
    _reconnect();
  }

  @override
  void onConnectionStateChanged(bool isConnected) {
    debugPrint("[GeminiStreaming] Internet connection changed: $isConnected, status: $_status");
    _isConnected = isConnected;
    if (isConnected) {
      if (_status == PureSocketStatus.connected || _status == PureSocketStatus.connecting) {
        return;
      }
      _reconnect();
    } else {
      _internetLostDelayTimer?.cancel();
      _internetLostDelayTimer = Timer(const Duration(seconds: 60), () async {
        if (_isConnected) return;
        await disconnect();
        _listener?.onInternetConnectionFailed();
      });
    }
  }
}

/// Streaming STT socket that sends audio immediately and receives transcripts in real-time
class PureStreamingSttSocket implements IPureSocket {
  StreamSubscription<bool>? _connectionStateListener;
  bool _isConnected = ConnectivityService().isConnected;
  Timer? _internetLostDelayTimer;
  Timer? _keepAliveTimer;

  WebSocketChannel? _channel;

  final StreamingSttConfig config;

  PureSocketStatus _status = PureSocketStatus.notConnected;
  @override
  PureSocketStatus get status => _status;

  IPureSocketListener? _listener;

  int _retries = 0;
  double _audioOffsetSeconds = 0;

  // Buffer for accumulating small frames before sending
  final List<Uint8List> _frameBuffer = [];
  int _bufferedBytes = 0;

  PureStreamingSttSocket({required this.config}) {
    _connectionStateListener = ConnectivityService().onConnectionChange.listen((bool isConnected) {
      onConnectionStateChanged(isConnected);
    });
  }

  @override
  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  @override
  Future<bool> connect() async {
    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return false;
    }

    debugPrint("[StreamingSTT] Connecting to ${config.serviceId}...");
    _status = PureSocketStatus.connecting;

    try {
      _channel = IOWebSocketChannel.connect(
        config.wsUrl,
        headers: config.headers,
        pingInterval: const Duration(seconds: 20),
        connectTimeout: const Duration(seconds: 15),
      );

      await _channel!.ready;

      _status = PureSocketStatus.connected;
      _retries = 0;
      onConnected();

      _channel!.stream.listen(
        _handleMessage,
        onError: (err, trace) => onError(err, trace),
        onDone: () => onClosed(_channel?.closeCode),
        cancelOnError: true,
      );

      _startKeepAlive();

      return true;
    } on TimeoutException catch (e) {
      debugPrint("[StreamingSTT] Connection timeout: $e");
      _status = PureSocketStatus.notConnected;
      return false;
    } on SocketException catch (e) {
      debugPrint("[StreamingSTT] Socket error: $e");
      _status = PureSocketStatus.notConnected;
      return false;
    } on WebSocketChannelException catch (e) {
      debugPrint("[StreamingSTT] WebSocket error: $e");
      _status = PureSocketStatus.notConnected;
      return false;
    } catch (e) {
      debugPrint("[StreamingSTT] Connection error: $e");
      _status = PureSocketStatus.notConnected;
      return false;
    }
  }

  void _startKeepAlive() {
    if (!config.sendKeepAlive) return;

    _keepAliveTimer?.cancel();
    _keepAliveTimer = Timer.periodic(config.keepAliveInterval, (_) {
      if (_status == PureSocketStatus.connected && _channel != null) {
        try {
          _channel!.sink.add(jsonEncode({'type': 'KeepAlive'}));
        } catch (e) {
          debugPrint("[StreamingSTT] Keep-alive error: $e");
        }
      }
    });
  }

  void _handleMessage(dynamic message) {
    if (message is! String) {
      debugPrint("[StreamingSTT] Non-string message received");
      return;
    }

    try {
      final json = jsonDecode(message);

      // Handle Deepgram-specific message types
      if (json is Map && json.containsKey('type')) {
        final type = json['type'];
        if (type == 'Metadata' || type == 'UtteranceEnd') {
          debugPrint("[StreamingSTT] Received $type message");
          return;
        }
        if (type != 'Results') {
          return;
        }
      }

      // Parse using schema
      final result = SttTranscriptionResult.fromJsonWithSchema(
        json,
        config.responseSchema,
        audioOffsetSeconds: 0, // Streaming providers usually provide absolute timestamps
      );

      if (result.isNotEmpty) {
        // Update offset based on latest segment
        if (result.segments.isNotEmpty) {
          _audioOffsetSeconds = result.segments.last.end;
        }

        // Aggregate words by speaker (matching backend behavior)
        final segments = <Map<String, dynamic>>[];
        for (final segment in result.segments) {
          if (segment.text.trim().isEmpty) continue;

          // Format speaker as SPEAKER_{id} to match backend format
          final speakerId = segment.speakerId ?? 0;
          final speaker = 'SPEAKER_$speakerId';

          if (segments.isEmpty || segments.last['speaker'] != speaker) {
            // New segment for different speaker
            segments.add({
              'text': segment.text.trim(),
              'speaker': speaker,
              'speaker_id': speakerId,
              'is_user': false,
              'start': segment.start,
              'end': segment.end,
              'person_id': null,
            });
          } else {
            // Same speaker - append to last segment
            final last = segments.last;
            last['text'] = '${last['text']} ${segment.text.trim()}';
            last['end'] = segment.end;
          }
        }

        if (segments.isNotEmpty) {
          onMessage(jsonEncode(segments));
        }
      }
    } catch (e, trace) {
      debugPrint("[StreamingSTT] Parse error: $e");
      debugPrintStack(stackTrace: trace);
    }
  }

  @override
  void send(dynamic message) {
    if (_status != PureSocketStatus.connected || _channel == null) {
      return;
    }

    Uint8List audioData;
    if (message is Uint8List) {
      audioData = message;
    } else if (message is List<int>) {
      audioData = Uint8List.fromList(message);
    } else {
      debugPrint("[StreamingSTT] Unsupported message type: ${message.runtimeType}");
      return;
    }

    // Buffer frames if minimum bytes threshold is set
    if (config.minBytesBeforeSend > 0) {
      _frameBuffer.add(audioData);
      _bufferedBytes += audioData.length;

      if (_bufferedBytes < config.minBytesBeforeSend) {
        return;
      }

      // Combine buffered frames
      final combined = Uint8List(_bufferedBytes);
      int offset = 0;
      for (final frame in _frameBuffer) {
        combined.setRange(offset, offset + frame.length, frame);
        offset += frame.length;
      }
      _frameBuffer.clear();
      _bufferedBytes = 0;
      audioData = combined;
    }

    // Transcode if needed (e.g., opus to raw PCM)
    if (config.transcoder != null) {
      try {
        audioData = config.transcoder!.transcodeFrames([audioData]);
      } catch (e) {
        debugPrint("[StreamingSTT] Transcode error: $e");
        return;
      }
    }

    // Send immediately to streaming endpoint
    try {
      _channel!.sink.add(audioData);
    } catch (e) {
      debugPrint("[StreamingSTT] Send error: $e");
    }
  }

  /// Send close signal to streaming provider (e.g., Deepgram's CloseStream)
  void sendCloseSignal() {
    if (_status == PureSocketStatus.connected && _channel != null) {
      try {
        _channel!.sink.add(jsonEncode({'type': 'CloseStream'}));
      } catch (e) {
        debugPrint("[StreamingSTT] Close signal error: $e");
      }
    }
  }

  @override
  Future disconnect() async {
    _keepAliveTimer?.cancel();
    sendCloseSignal();

    // Give time for final results
    await Future.delayed(const Duration(milliseconds: 500));

    _channel?.sink.close();
    _status = PureSocketStatus.disconnected;
    debugPrint("[StreamingSTT] Disconnected");
    onClosed();
  }

  Future _cleanUp() async {
    _internetLostDelayTimer?.cancel();
    _connectionStateListener?.cancel();
    _keepAliveTimer?.cancel();
    _frameBuffer.clear();
    _bufferedBytes = 0;
    _audioOffsetSeconds = 0;
  }

  @override
  Future stop() async {
    await disconnect();
    await _cleanUp();
  }

  @override
  void onConnected() {
    debugPrint("[StreamingSTT] Connected to ${config.serviceId}");
    _listener?.onConnected();
  }

  @override
  void onMessage(dynamic message) {
    _listener?.onMessage(message);
  }

  @override
  void onClosed([int? closeCode]) {
    _status = PureSocketStatus.disconnected;
    debugPrint("[StreamingSTT] Closed with code: $closeCode");
    _listener?.onClosed(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    debugPrint("[StreamingSTT] Error: $err");
    _listener?.onError(err, trace);
  }

  void _reconnect() async {
    debugPrint("[StreamingSTT] Reconnecting...${_retries + 1}...");
    const int initialBackoffTimeMs = 1000;
    const double multiplier = 1.5;
    const int maxRetries = 8;

    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return;
    }

    await _cleanUp();

    var ok = await connect();
    if (ok) return;

    int waitInMilliseconds = pow(multiplier, _retries).toInt() * initialBackoffTimeMs;
    await Future.delayed(Duration(milliseconds: waitInMilliseconds));
    _retries++;
    if (_retries > maxRetries) {
      debugPrint("[StreamingSTT] Max retries reached");
      _listener?.onMaxRetriesReach();
      return;
    }
    _reconnect();
  }

  @override
  void onConnectionStateChanged(bool isConnected) {
    debugPrint("[StreamingSTT] Internet connection changed: $isConnected, status: $_status");
    _isConnected = isConnected;
    if (isConnected) {
      if (_status == PureSocketStatus.connected || _status == PureSocketStatus.connecting) {
        return;
      }
      _reconnect();
    } else {
      _internetLostDelayTimer?.cancel();
      _internetLostDelayTimer = Timer(const Duration(seconds: 60), () async {
        if (_isConnected) return;
        await disconnect();
        _listener?.onInternetConnectionFailed();
      });
    }
  }
}
