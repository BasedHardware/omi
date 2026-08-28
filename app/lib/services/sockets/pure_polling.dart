import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:omi/models/stt_result.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/utils/audio/audio_transcoder.dart';
import 'package:omi/utils/debug_log_manager.dart';
import 'package:omi/utils/logger.dart';

enum PurePollingStatus { notConnected, connecting, connected, disconnected }

class AudioPollingConfig {
  final Duration bufferDuration;
  final int minBufferSizeBytes;
  final String? serviceId;
  final IAudioTranscoder? transcoder;
  // Ceiling on how much unflushed audio we hold in memory
  // while the custom STT endpoint is unreachable. ~10 minutes of 16kHz/16-bit
  // mono PCM (32000 B/s); oldest frames are dropped past this to keep memory
  // bounded during a long outage instead of buffering forever.
  final int maxBufferBytes;

  const AudioPollingConfig({
    this.bufferDuration = const Duration(seconds: 3),
    this.minBufferSizeBytes = 8000,
    this.serviceId,
    this.transcoder,
    this.maxBufferBytes = 19200000,
  });
}

abstract class ISttProvider {
  Future<SttTranscriptionResult?> transcribe(Uint8List audioData, {double audioOffsetSeconds = 0});

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

  // Local buffering state, exposed so the recording UI can
  // show "offline, buffering" instead of silently sitting on "Listening"
  // while transcribe() keeps failing. Set on the first failed flush after a
  // success, cleared on the next successful one.
  DateTime? _bufferingSince;
  int _consecutiveFailures = 0;

  DateTime? get bufferingSince => _bufferingSince;
  int get consecutiveFailures => _consecutiveFailures;
  bool get isBuffering => _bufferingSince != null;
  int get bufferedBytes => _totalBufferBytes;

  PurePollingSocket({required this.config, required this.sttProvider});

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
      DebugLogManager.logWarning('polling_socket_connect_error', {'service_id': serviceId, 'error': e.toString()});
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
        Logger.debug("[Polling] Transcoding error: $e");
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
      final result = await sttProvider.transcribe(audioData, audioOffsetSeconds: _audioOffsetSeconds);
      _bufferingSince = null;
      _consecutiveFailures = 0;
      if (result != null && result.isNotEmpty) {
        if (result.segments.isNotEmpty) {
          _audioOffsetSeconds = result.segments.last.end;
        }
        final segmentsJson =
            result.segments.where((s) => s.text.trim().isNotEmpty).map((s) => s.toTranscriptSegmentJson()).toList();
        if (segmentsJson.isNotEmpty) {
          onMessage(jsonEncode(segmentsJson));
        }
      }
    } catch (e, trace) {
      CustomSttLogService.instance.error(serviceId, 'Transcription error: $e');
      DebugLogManager.logError(e, trace, 'polling_socket_transcription_error', {'service_id': serviceId});
      _consecutiveFailures++;
      _bufferingSince ??= DateTime.now();
      _requeueFrames(frames);
      // Do NOT call onError()/propagate this as a fatal
      // socket error here. sttProvider.transcribe() already retries
      // transient failures internally; a failure this far up means the STT
      // endpoint is genuinely unreachable right now. The old behavior
      // reported this as a fatal error, which CompositeTranscriptionSocket
      // treated as "tear down both sockets" — killing the healthy
      // raw-audio/secondary channel too and forcing a full reconnect every
      // time custom STT hiccuped. Instead: keep the frames buffered above
      // (capped by maxBufferBytes) and let the next timer tick retry, so a
      // transient outage is invisible and a real one just keeps buffering
      // until the endpoint comes back.
    } finally {
      _isProcessing = false;
    }
  }

  /// Puts frames that failed to transcribe back at the front of the buffer
  /// (ahead of anything captured since the attempt started), trimming the
  /// oldest audio if the combined buffer now exceeds [AudioPollingConfig.maxBufferBytes].
  void _requeueFrames(List<Uint8List> frames) {
    _audioFrames.insertAll(0, frames);

    var droppedBytes = 0;
    while (_totalBufferBytes > config.maxBufferBytes && _audioFrames.isNotEmpty) {
      droppedBytes += _audioFrames.removeAt(0).length;
    }
    if (droppedBytes > 0) {
      final serviceId = config.serviceId ?? 'Polling';
      CustomSttLogService.instance.warning(
        serviceId,
        'Buffer cap exceeded while offline, dropped $droppedBytes bytes of oldest audio',
      );
      DebugLogManager.logWarning('polling_socket_buffer_overflow', {
        'service_id': serviceId,
        'dropped_bytes': droppedBytes,
      });
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
    DebugLogManager.logEvent('polling_socket_stopping', {'service_id': config.serviceId ?? 'Polling'});
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
    DebugLogManager.logError(err, trace, 'polling_socket_error', {'service_id': config.serviceId ?? 'Polling'});
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
      Logger.debug("[Polling] Unsupported message type: ${message.runtimeType}");
    }
  }

  Future<void> flushNow() async {
    await _flushBuffer();
  }
}
