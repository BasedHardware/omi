import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/models/stt_response_schema.dart';
import 'package:omi/models/stt_result.dart';
import 'package:omi/utils/audio/audio_transcoder.dart';
import 'package:omi/utils/debug_log_manager.dart';

/// Configuration for streaming STT WebSocket connections
class StreamingSttConfig {
  final String url;
  final Map<String, String> headers;
  final SttResponseSchema responseSchema;
  final IAudioTranscoder? transcoder;
  final String serviceId;
  final int minBytesBeforeSend;
  final bool sendKeepAlive;
  final Duration keepAliveInterval;

  const StreamingSttConfig({
    required this.url,
    this.headers = const {},
    required this.responseSchema,
    this.transcoder,
    this.serviceId = 'streaming-stt',
    this.minBytesBeforeSend = 0,
    this.sendKeepAlive = false,
    this.keepAliveInterval = const Duration(seconds: 10),
  });

  /// Alias for backward compatibility
  String get wsUrl => url;

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
      url: wsUrl,
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

  double _audioOffsetSeconds = 0;
  bool _setupSent = false;

  final List<Uint8List> _frameBuffer = [];
  int _bufferedBytes = 0;
  static const int _minBytesBeforeSend = 16000;

  GeminiStreamingSttSocket({
    required this.apiKey,
    this.model = 'gemini-2.5-flash-native-audio-preview-12-2025',
    this.language = 'en',
    this.sampleRate = 16000,
    this.transcoder,
  });

  @override
  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  String get _wsUrl =>
      'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key=$apiKey';

  @override
  Future<bool> connect() async {
    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return false;
    }

    CustomSttLogService.instance.info('GeminiStreaming', 'Connecting...');
    _status = PureSocketStatus.connecting;

    try {
      _channel = IOWebSocketChannel.connect(
        _wsUrl,
        pingInterval: const Duration(seconds: 20),
        connectTimeout: const Duration(seconds: 15),
      );

      await _channel!.ready;

      _status = PureSocketStatus.connected;
      _setupSent = false;
      DebugLogManager.logEvent('gemini_streaming_connected', {
        'model': model,
        'language': language,
        'sample_rate': sampleRate,
      });

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
      CustomSttLogService.instance.error('GeminiStreaming', 'Connection timeout: $e');
      DebugLogManager.logWarning('gemini_streaming_connect_timeout', {'error': e.toString()});
      _status = PureSocketStatus.notConnected;
      return false;
    } on SocketException catch (e) {
      CustomSttLogService.instance.error('GeminiStreaming', 'Socket error: $e');
      DebugLogManager.logWarning('gemini_streaming_socket_error', {'error': e.toString()});
      _status = PureSocketStatus.notConnected;
      return false;
    } on WebSocketChannelException catch (e) {
      CustomSttLogService.instance.error('GeminiStreaming', 'WebSocket error: $e');
      DebugLogManager.logWarning('gemini_streaming_websocket_error', {'error': e.toString()});
      _status = PureSocketStatus.notConnected;
      return false;
    } catch (e) {
      CustomSttLogService.instance.error('GeminiStreaming', 'Connection error: $e');
      DebugLogManager.logWarning('gemini_streaming_connect_error', {'error': e.toString()});
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
          'responseModalities': ['AUDIO'],
        },
        'inputAudioTranscription': {},
      }
    };

    try {
      _channel!.sink.add(jsonEncode(setupMessage));
      _setupSent = true;
      CustomSttLogService.instance.info('GeminiStreaming', 'Setup message sent');
    } catch (e) {
      CustomSttLogService.instance.error('GeminiStreaming', 'Failed to send setup: $e');
    }
  }

  void _handleMessage(dynamic message) {
    String messageStr;
    if (message is String) {
      messageStr = message;
    } else if (message is List<int>) {
      // Binary WebSocket frame - decode as UTF-8
      try {
        messageStr = utf8.decode(message);
      } catch (e) {
        debugPrint("[GeminiStreaming] Failed to decode binary message: $e");
        return;
      }
    } else {
      debugPrint("[GeminiStreaming] Unsupported message type: ${message.runtimeType}");
      return;
    }

    try {
      final json = jsonDecode(messageStr);

      if (json.containsKey('setupComplete')) {
        CustomSttLogService.instance.info('GeminiStreaming', 'Setup complete');
        return;
      }

      if (json.containsKey('toolCall')) {
        return;
      }

      // Handle server content with inputTranscription
      final serverContent = json['serverContent'];
      if (serverContent == null) return;

      // Check for turn complete
      if (serverContent['turnComplete'] == true) {
        CustomSttLogService.instance.info('GeminiStreaming', 'Turn complete');
        return;
      }

      // Extract input transcription (the new response format)
      final inputTranscription = serverContent['inputTranscription'];
      String? text;
      if (inputTranscription != null) {
        text = inputTranscription['text'] as String?;
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
      CustomSttLogService.instance.error('GeminiStreaming', 'Parse error: $e');
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
      CustomSttLogService.instance.warning('GeminiStreaming', 'Unsupported message type: ${message.runtimeType}');
      return;
    }

    _frameBuffer.add(audioData);
    _bufferedBytes += audioData.length;

    if (_bufferedBytes < _minBytesBeforeSend) {
      return;
    }

    Uint8List pcmData;
    if (transcoder != null) {
      // Transcode individual frames (important for Opus which needs frame boundaries)
      try {
        pcmData = transcoder!.transcodeFrames(_frameBuffer);
      } catch (e) {
        CustomSttLogService.instance.error('GeminiStreaming', 'Transcode error: $e');
        _frameBuffer.clear();
        _bufferedBytes = 0;
        return;
      }
    } else {
      // Only combine if no transcoding needed (raw PCM)
      pcmData = Uint8List(_bufferedBytes);
      int offset = 0;
      for (final frame in _frameBuffer) {
        pcmData.setRange(offset, offset + frame.length, frame);
        offset += frame.length;
      }
    }
    _frameBuffer.clear();
    _bufferedBytes = 0;

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
      CustomSttLogService.instance.error('GeminiStreaming', 'Send error: $e');
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
    CustomSttLogService.instance.info('GeminiStreaming', 'Disconnected');
    onClosed();
  }

  @override
  Future stop() async {
    DebugLogManager.logEvent('gemini_streaming_stopping', {});
    await disconnect();
    _frameBuffer.clear();
    _bufferedBytes = 0;
    _audioOffsetSeconds = 0;
    _setupSent = false;
  }

  @override
  void onConnected() {
    CustomSttLogService.instance.info('GeminiStreaming', 'Connected');
    _listener?.onConnected();
  }

  @override
  void onMessage(dynamic message) {
    _listener?.onMessage(message);
  }

  @override
  void onClosed([int? closeCode]) {
    _status = PureSocketStatus.disconnected;
    CustomSttLogService.instance.warning('GeminiStreaming', 'Closed with code: $closeCode');
    DebugLogManager.logEvent('gemini_streaming_closed', {
      'close_code': closeCode ?? -1,
    });
    _listener?.onClosed(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    CustomSttLogService.instance.error('GeminiStreaming', 'Error: $err');
    DebugLogManager.logError(err, trace, 'gemini_streaming_error');
    _listener?.onError(err, trace);
  }
}

/// Streaming STT socket that sends audio immediately and receives transcripts in real-time
class PureStreamingSttSocket implements IPureSocket {
  Timer? _keepAliveTimer;

  WebSocketChannel? _channel;

  final StreamingSttConfig config;

  PureSocketStatus _status = PureSocketStatus.notConnected;
  @override
  PureSocketStatus get status => _status;

  IPureSocketListener? _listener;

  double _audioOffsetSeconds = 0;

  // Buffer for accumulating small frames before sending
  final List<Uint8List> _frameBuffer = [];
  int _bufferedBytes = 0;

  PureStreamingSttSocket({required this.config});

  @override
  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  @override
  Future<bool> connect() async {
    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return false;
    }

    CustomSttLogService.instance.info(config.serviceId, 'Connecting...');
    _status = PureSocketStatus.connecting;

    try {
      _channel = IOWebSocketChannel.connect(
        config.url,
        headers: config.headers,
        pingInterval: const Duration(seconds: 20),
        connectTimeout: const Duration(seconds: 15),
      );

      await _channel!.ready;

      _status = PureSocketStatus.connected;
      DebugLogManager.logEvent('streaming_stt_connected', {
        'service_id': config.serviceId,
        'url': config.url,
      });
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
      CustomSttLogService.instance.error(config.serviceId, 'Connection timeout: $e');
      DebugLogManager.logWarning('streaming_stt_connect_timeout', {
        'service_id': config.serviceId,
        'error': e.toString(),
      });
      _status = PureSocketStatus.notConnected;
      return false;
    } on SocketException catch (e) {
      CustomSttLogService.instance.error(config.serviceId, 'Socket error: $e');
      DebugLogManager.logWarning('streaming_stt_socket_error', {
        'service_id': config.serviceId,
        'error': e.toString(),
      });
      _status = PureSocketStatus.notConnected;
      return false;
    } on WebSocketChannelException catch (e) {
      CustomSttLogService.instance.error(config.serviceId, 'WebSocket error: $e');
      DebugLogManager.logWarning('streaming_stt_websocket_error', {
        'service_id': config.serviceId,
        'error': e.toString(),
      });
      _status = PureSocketStatus.notConnected;
      return false;
    } catch (e) {
      CustomSttLogService.instance.error(config.serviceId, 'Connection error: $e');
      DebugLogManager.logWarning('streaming_stt_connect_error', {
        'service_id': config.serviceId,
        'error': e.toString(),
      });
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
          CustomSttLogService.instance.warning(config.serviceId, 'Keep-alive error: $e');
        }
      }
    });
  }

  void _handleMessage(dynamic message) {
    if (message is! String) {
      CustomSttLogService.instance.warning(config.serviceId, 'Non-string message received');
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
        audioOffsetSeconds: 0,
      );

      if (result.isNotEmpty) {
        if (result.segments.isNotEmpty) {
          _audioOffsetSeconds = result.segments.last.end;
        }

        // Aggregate words by speaker (matching backend TranscriptSegment format)
        final segments = <Map<String, dynamic>>[];
        for (final segment in result.segments) {
          if (segment.text.trim().isEmpty) continue;

          final speakerId = segment.speakerId;
          final speaker = 'SPEAKER_$speakerId';

          if (segments.isEmpty || segments.last['speaker'] != speaker) {
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
      CustomSttLogService.instance.error(config.serviceId, 'Parse error: $e');
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
      CustomSttLogService.instance.warning(config.serviceId, 'Unsupported message type: ${message.runtimeType}');
      return;
    }

    // Buffer frames if minimum bytes threshold is set
    if (config.minBytesBeforeSend > 0) {
      _frameBuffer.add(audioData);
      _bufferedBytes += audioData.length;

      if (_bufferedBytes < config.minBytesBeforeSend) {
        return;
      }

      // Transcode individual frames (important for Opus which needs frame boundaries)
      if (config.transcoder != null) {
        try {
          audioData = config.transcoder!.transcodeFrames(_frameBuffer);
        } catch (e) {
          CustomSttLogService.instance.error(config.serviceId, 'Transcode error: $e');
          _frameBuffer.clear();
          _bufferedBytes = 0;
          return;
        }
      } else {
        // Only combine if no transcoding needed (raw PCM)
        final combined = Uint8List(_bufferedBytes);
        int offset = 0;
        for (final frame in _frameBuffer) {
          combined.setRange(offset, offset + frame.length, frame);
          offset += frame.length;
        }
        audioData = combined;
      }
      _frameBuffer.clear();
      _bufferedBytes = 0;
    } else {
      // No buffering - transcode single frame
      if (config.transcoder != null) {
        try {
          audioData = config.transcoder!.transcodeFrames([audioData]);
        } catch (e) {
          CustomSttLogService.instance.error(config.serviceId, 'Transcode error: $e');
          return;
        }
      }
    }

    // Send immediately to streaming endpoint
    try {
      _channel!.sink.add(audioData);
    } catch (e) {
      CustomSttLogService.instance.error(config.serviceId, 'Send error: $e');
    }
  }

  /// Send close signal to streaming provider (e.g., Deepgram's CloseStream)
  void sendCloseSignal() {
    if (_status == PureSocketStatus.connected && _channel != null) {
      try {
        _channel!.sink.add(jsonEncode({'type': 'CloseStream'}));
      } catch (e) {
        CustomSttLogService.instance.warning(config.serviceId, 'Close signal error: $e');
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
    CustomSttLogService.instance.info(config.serviceId, 'Disconnected');
    onClosed();
  }

  @override
  Future stop() async {
    DebugLogManager.logEvent('streaming_stt_stopping', {
      'service_id': config.serviceId,
    });
    await disconnect();
    _keepAliveTimer?.cancel();
    _frameBuffer.clear();
    _bufferedBytes = 0;
    _audioOffsetSeconds = 0;
  }

  @override
  void onConnected() {
    CustomSttLogService.instance.info(config.serviceId, 'Connected');
    _listener?.onConnected();
  }

  @override
  void onMessage(dynamic message) {
    _listener?.onMessage(message);
  }

  @override
  void onClosed([int? closeCode]) {
    _status = PureSocketStatus.disconnected;
    CustomSttLogService.instance.warning(config.serviceId, 'Closed with code: $closeCode');
    DebugLogManager.logEvent('streaming_stt_closed', {
      'service_id': config.serviceId,
      'close_code': closeCode ?? -1,
    });
    _listener?.onClosed(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    CustomSttLogService.instance.error(config.serviceId, 'Error: $err');
    DebugLogManager.logError(err, trace, 'streaming_stt_error', {
      'service_id': config.serviceId,
    });
    _listener?.onError(err, trace);
  }
}
