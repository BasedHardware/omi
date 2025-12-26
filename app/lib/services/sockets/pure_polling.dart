import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/utils/audio/audio_transcoder.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/models/stt_result.dart';
import 'package:omi/utils/debug_log_manager.dart';

enum PurePollingStatus { notConnected, connecting, connected, disconnected }

class AudioPollingConfig {
  final Duration bufferDuration;
  final int minBufferSizeBytes;
  final String? serviceId;
  final IAudioTranscoder? transcoder;

  const AudioPollingConfig({
    this.bufferDuration = const Duration(seconds: 3),
    this.minBufferSizeBytes = 8000,
    this.serviceId,
    this.transcoder,
  });
}

abstract class ISttProvider {
  Future<SttTranscriptionResult?> transcribe(
    Uint8List audioData, {
    double audioOffsetSeconds = 0,
  });

  void dispose();
}

class PurePollingSocket implements IPureSocket {
  Timer? _bufferFlushTimer;

  final AudioPollingConfig config;
  final ISttProvider sttProvider;

  PurePollingStatus _status = PurePollingStatus.notConnected;
  PurePollingStatus get pollingStatus => _status;

  @override
  PureSocketStatus get status {
    switch (_status) {
      case PurePollingStatus.notConnected:
        return PureSocketStatus.notConnected;
      case PurePollingStatus.connecting:
        return PureSocketStatus.connecting;
      case PurePollingStatus.connected:
        return PureSocketStatus.connected;
      case PurePollingStatus.disconnected:
        return PureSocketStatus.disconnected;
    }
  }

  IPureSocketListener? _listener;

  @override
  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  final List<Uint8List> _audioFrames = [];
  bool _isProcessing = false;
  double _audioOffsetSeconds = 0;

  PurePollingSocket({
    required this.config,
    required this.sttProvider,
  });

  @override
  Future<bool> connect() async {
    if (_status == PurePollingStatus.connecting || _status == PurePollingStatus.connected) {
      return false;
    }

    final serviceId = config.serviceId ?? 'Polling';
    CustomSttLogService.instance.info(serviceId, 'Connecting...');
    _status = PurePollingStatus.connecting;

    try {
      _status = PurePollingStatus.connected;
      CustomSttLogService.instance.info(serviceId, 'Connected');
      DebugLogManager.logEvent('polling_socket_connected', {
        'service_id': serviceId,
        'buffer_duration_ms': config.bufferDuration.inMilliseconds,
        'min_buffer_bytes': config.minBufferSizeBytes,
      });
      onConnected();

      _startBufferFlushTimer();
      return true;
    } catch (e) {
      CustomSttLogService.instance.error(serviceId, 'Connection error: $e');
      DebugLogManager.logWarning('polling_socket_connect_error', {
        'service_id': serviceId,
        'error': e.toString(),
      });
      _status = PurePollingStatus.notConnected;
      return false;
    }
  }

  void _startBufferFlushTimer() {
    _bufferFlushTimer?.cancel();
    _bufferFlushTimer = Timer.periodic(config.bufferDuration, (_) {
      _flushBuffer();
    });
  }

  void setAudioOffset(double offsetSeconds) {
    _audioOffsetSeconds = offsetSeconds;
  }

  double get audioOffset => _audioOffsetSeconds;

  int get _totalBufferBytes => _audioFrames.fold<int>(0, (sum, frame) => sum + frame.length);

  Future<void> _flushBuffer() async {
    if (_audioFrames.isEmpty || _status != PurePollingStatus.connected) {
      return;
    }

    if (_totalBufferBytes < config.minBufferSizeBytes || _isProcessing) {
      return;
    }

    _isProcessing = true;

    final frames = List<Uint8List>.from(_audioFrames);
    _audioFrames.clear();

    Uint8List audioData;

    if (config.transcoder != null) {
      try {
        audioData = config.transcoder!.transcodeFrames(frames);
      } catch (e, trace) {
        debugPrint("[Polling] Transcoding error: $e");
        _isProcessing = false;
        onError(e, trace);
        return;
      }
    } else {
      final totalLength = frames.fold<int>(0, (sum, frame) => sum + frame.length);
      audioData = Uint8List(totalLength);
      int offset = 0;
      for (final frame in frames) {
        audioData.setRange(offset, offset + frame.length, frame);
        offset += frame.length;
      }
    }

    final serviceId = config.serviceId ?? 'Polling';
    try {
      final result = await sttProvider.transcribe(
        audioData,
        audioOffsetSeconds: _audioOffsetSeconds,
      );
      if (result != null && result.isNotEmpty) {
        if (result.segments.isNotEmpty) {
          _audioOffsetSeconds = result.segments.last.end;
        }
        final segmentsJson = result.segments
            .where((s) => s.text.trim().isNotEmpty)
            .map((s) => {
                  'text': s.text.trim(),
                  'speaker': 'SPEAKER_${s.speakerId}',
                  'speaker_id': s.speakerId,
                  'is_user': false,
                  'start': s.start,
                  'end': s.end,
                })
            .toList();
        if (segmentsJson.isNotEmpty) {
          onMessage(jsonEncode(segmentsJson));
        }
      }
    } catch (e, trace) {
      CustomSttLogService.instance.error(serviceId, 'Transcription error: $e');
      DebugLogManager.logError(e, trace, 'polling_socket_transcription_error', {
        'service_id': serviceId,
      });
      onError(e, trace);
    } finally {
      _isProcessing = false;
    }
  }

  @override
  Future disconnect() async {
    _bufferFlushTimer?.cancel();

    if (_audioFrames.isNotEmpty && !_isProcessing) {
      await _flushBuffer();
    }

    _status = PurePollingStatus.disconnected;
    CustomSttLogService.instance.info(config.serviceId ?? 'Polling', 'Disconnected');
    onClosed();
  }

  @override
  Future stop() async {
    DebugLogManager.logEvent('polling_socket_stopping', {
      'service_id': config.serviceId ?? 'Polling',
    });
    await disconnect();
    _bufferFlushTimer?.cancel();
    _audioFrames.clear();
    _audioOffsetSeconds = 0;
    sttProvider.dispose();
  }

  @override
  void onClosed([int? closeCode]) {
    _status = PurePollingStatus.disconnected;
    CustomSttLogService.instance.info(config.serviceId ?? 'Polling', 'Closed');
    DebugLogManager.logEvent('polling_socket_closed', {
      'service_id': config.serviceId ?? 'Polling',
      'close_code': closeCode ?? -1,
    });
    _listener?.onClosed(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    CustomSttLogService.instance.error(config.serviceId ?? 'Polling', 'Error: $err');
    DebugLogManager.logError(err, trace, 'polling_socket_error', {
      'service_id': config.serviceId ?? 'Polling',
    });
    debugPrintStack(stackTrace: trace);
    _listener?.onError(err, trace);
  }

  @override
  void onMessage(dynamic message) {
    _listener?.onMessage(message);
  }

  @override
  void onConnected() {
    _listener?.onConnected();
  }

  @override
  void send(dynamic message) {
    if (message is Uint8List) {
      _audioFrames.add(message);
    } else if (message is List<int>) {
      _audioFrames.add(Uint8List.fromList(message));
    } else {
      debugPrint("[Polling] Unsupported message type: ${message.runtimeType}");
    }
  }

  Future<void> flushNow() async {
    await _flushBuffer();
  }
}
