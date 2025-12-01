import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/utils/audio/audio_transcoder.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/models/stt_result.dart';
import 'package:omi/services/connectivity_service.dart';

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

    debugPrint("[Polling] Connecting${config.serviceId != null ? ' to ${config.serviceId}' : ''}");
    _status = PurePollingStatus.connecting;

    try {
      _status = PurePollingStatus.connected;
      _retries = 0;
      onConnected();

      _startBufferFlushTimer();
      return true;
    } catch (e) {
      debugPrint("[Polling] Connection error: $e");
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
      debugPrint("[Polling] Transcription error: $e");
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
    debugPrint("[Polling] Disconnected");
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
    await disconnect();
    await _cleanUp();
    sttProvider.dispose();
  }

  @override
  void onClosed([int? closeCode]) {
    _status = PurePollingStatus.disconnected;
    debugPrint("[Polling] Closed");
    _listener?.onClosed(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    debugPrint("[Polling] Error: $err");
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
    debugPrint("[Polling] Reconnecting...${_retries + 1}...");
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
      debugPrint("[Polling] Max retries reached: $maxRetries");
      _listener?.onMaxRetriesReach();
      return;
    }
    _reconnect();
  }

  @override
  void onConnectionStateChanged(bool isConnected) {
    debugPrint("[Polling] Internet connection changed: $isConnected, status: $_status");
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
        await disconnect();
        _listener?.onInternetConnectionFailed();
      });
    }
  }
}
