import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/utils/audio/audio_transcoder.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/models/stt_result.dart';
import 'package:omi/services/connectivity_service.dart';
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
  StreamSubscription<bool>? _connectionStateListener;
  bool _isConnected = ConnectivityService().isConnected;
  Timer? _internetLostDelayTimer;
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
  int _retries = 0;

  PurePollingSocket({
    required this.config,
    required this.sttProvider,
  }) {
    _connectionStateListener = ConnectivityService().onConnectionChange.listen((bool isConnected) {
      onConnectionStateChanged(isConnected);
    });
  }

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
      _retries = 0;
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

  Future _cleanUp() async {
    _internetLostDelayTimer?.cancel();
    _connectionStateListener?.cancel();
    _bufferFlushTimer?.cancel();
    _audioFrames.clear();
    _audioOffsetSeconds = 0;
  }

  @override
  Future stop() async {
    DebugLogManager.logEvent('polling_socket_stopping', {
      'service_id': config.serviceId ?? 'Polling',
    });
    await disconnect();
    await _cleanUp();
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

  void _reconnect() async {
    CustomSttLogService.instance.info(config.serviceId ?? 'Polling', 'Reconnecting... attempt ${_retries + 1}');
    DebugLogManager.logEvent('polling_socket_reconnect_attempt', {
      'service_id': config.serviceId ?? 'Polling',
      'attempt': _retries + 1,
      'max_retries': 8,
    });
    const int initialBackoffTimeMs = 1000;
    const double multiplier = 1.5;
    const int maxRetries = 8;

    if (_status == PurePollingStatus.connecting || _status == PurePollingStatus.connected) {
      debugPrint("[Polling] Cannot reconnect, status is $_status");
      return;
    }

    await _cleanUp();

    var ok = await connect();
    if (ok) return;

    int waitInMilliseconds = (multiplier * _retries).toInt() * initialBackoffTimeMs;
    await Future.delayed(Duration(milliseconds: waitInMilliseconds));
    _retries++;
    if (_retries > maxRetries) {
      CustomSttLogService.instance.error(config.serviceId ?? 'Polling', 'Max retries reached: $maxRetries');
      DebugLogManager.logWarning('polling_socket_max_retries', {
        'service_id': config.serviceId ?? 'Polling',
        'max_retries': maxRetries,
      });
      _listener?.onMaxRetriesReach();
      return;
    }
    _reconnect();
  }

  @override
  void onConnectionStateChanged(bool isConnected) {
    CustomSttLogService.instance.info(config.serviceId ?? 'Polling', 'Internet: $isConnected, status: $_status');
    DebugLogManager.logEvent('polling_socket_connection_state_changed', {
      'service_id': config.serviceId ?? 'Polling',
      'is_connected': isConnected,
      'socket_status': _status.toString(),
    });
    _isConnected = isConnected;
    if (isConnected) {
      if (_status == PurePollingStatus.connected || _status == PurePollingStatus.connecting) {
        return;
      }
      _reconnect();
    } else {
      _internetLostDelayTimer?.cancel();
      _internetLostDelayTimer = Timer(const Duration(seconds: 60), () async {
        if (_isConnected) return;
        DebugLogManager.logWarning('polling_socket_internet_lost_timeout', {
          'service_id': config.serviceId ?? 'Polling',
        });
        await disconnect();
        _listener?.onInternetConnectionFailed();
      });
    }
  }
}
