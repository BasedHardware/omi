import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_connection.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/logger.dart';
import 'package:opus_dart/opus_dart.dart';

class WebhookOnlySocketService implements IPureSocketListener, ITranscriptSegmentSocketService {
  final Map<Object, ITransctipSegmentSocketServiceListener> _listeners = {};

  SocketServiceState _state = SocketServiceState.disconnected;

  @override
  SocketServiceState get state => _state;

  int sampleRate;
  BleAudioCodec codec;
  String language;

  Timer? _batchTimer;
  final List<int> _audioBuffer = [];
  int _batchDelay = 60;
  int _keepAliveInterval = 30;
  late int _minBatchSize; // Calculated based on sample rate in constructor
  SimpleOpusDecoder? _opusDecoder; // For decoding Opus audio to PCM

  // BLE frame reassembly state (audio packets can span multiple BLE notifications)
  int _lastPacketIndex = -1;
  int _lastFrameId = -1;
  List<int> _pendingFrame = [];
  int _framesReceived = 0;
  int _framesLost = 0;

  Function()? onWebhookCalled;
  Function(Map<String, dynamic>)? onWebhookPayloadCapture;
  Function(String)? onWebhookError;

  WebhookOnlySocketService.create(
    this.sampleRate,
    this.codec,
    this.language,
  ) {
    final delayStr = SharedPreferencesUtil().webhookAudioBytesDelay;
    _batchDelay = int.tryParse(delayStr) ?? 60;

    final batteryLevel = SharedPreferencesUtil().batteryOptimizationLevel;
    _keepAliveInterval = _getKeepAliveIntervalForLevel(batteryLevel);

    // Calculate minimum batch size based on user's configured batch delay
    // At 16-bit PCM: sampleRate * 2 bytes/sample * batchDelay seconds
    // This respects the user's interval setting (e.g., 60s)
    _minBatchSize = (sampleRate * 2 * _batchDelay).toInt();

    // Initialize Opus decoder if device sends Opus-encoded audio
    if (codec.isOpusSupported()) {
      _opusDecoder = SimpleOpusDecoder(sampleRate: sampleRate, channels: 1);
      debugPrint('[WEBHOOK] Initialized Opus decoder for codec=$codec');
    }

    debugPrint('WebhookOnlySocketService: Batch delay=$_batchDelay s, KeepAlive=$_keepAliveInterval s, MinBatchSize=$_minBatchSize bytes');
  }

  int _getKeepAliveIntervalForLevel(int level) {
    switch (level) {
      case 0:
        return 10; // No optimization
      case 1:
        return 15; // Balanced
      case 2:
        return 30; // Aggressive (default)
      default:
        return 30;
    }
  }

  @override
  void subscribe(Object context, ITransctipSegmentSocketServiceListener listener) {
    _listeners.remove(context.hashCode);
    _listeners.putIfAbsent(context.hashCode, () => listener);
  }

  @override
  void unsubscribe(Object context) {
    _listeners.remove(context.hashCode);
  }

  @override
  Future start() async {
    final webhookUrl = SharedPreferencesUtil().webhookAudioBytes;

    if (webhookUrl.isEmpty) {
      throw Exception('Webhook URL is required for webhook-only mode');
    }

    _state = SocketServiceState.connected;
    debugPrint('WebhookOnlySocketService: Started (no WebSocket connection)');

    _notifyConnected();
    return;
  }

  @override
  Future stop({String? reason}) async {
    _batchTimer?.cancel();
    _batchTimer = null;

    // Flush any pending incomplete frame before stopping
    if (_pendingFrame.isNotEmpty) {
      debugPrint('[WEBHOOK] 🔊 Processing final pending frame (${_pendingFrame.length} bytes) before stop');
      _processCompleteOpusFrame(_pendingFrame);
    }

    // Only flush on explicit user stops, not on automatic stops (app background, reconnects, etc)
    // Explicit stops start with "stop" (user action), automatic stops are system-initiated
    final isExplicitStop = reason != null &&
        (reason.startsWith('stop') || reason == 'stop stream recording');

    if (isExplicitStop) {
      debugPrint('[WEBHOOK] 🛑 Explicit stop detected ($reason) - flushing buffer regardless of size');
      await _flushBuffer(forceFlush: true);
    } else {
      debugPrint('[WEBHOOK] ⚠️ Automatic stop ($reason) - only flushing if buffer >= min threshold');
      await _flushBuffer(forceFlush: false);
    }

    // Reset frame reassembly state
    _resetFrameReassemblyState();

    _listeners.clear();
    _state = SocketServiceState.disconnected;

    if (reason != null) {
      debugPrint('WebhookOnlySocketService stopped: $reason (frames received: $_framesReceived, lost: $_framesLost)');
    }
  }

  void _resetFrameReassemblyState() {
    _lastPacketIndex = -1;
    _lastFrameId = -1;
    _pendingFrame = [];
    _framesReceived = 0;
    _framesLost = 0;
  }

  @override
  Future send(dynamic message) async {
    if (message is List<int>) {
      // Check if this is a raw BLE packet with header (has 3+ bytes and needs reassembly)
      // or already processed audio data (from non-Opus codecs or pre-processed sources)
      if (codec.isOpusSupported() && message.length >= 3) {
        // This is a raw BLE packet - needs frame reassembly before decoding
        _processRawBlePacket(message);
      } else {
        // Non-Opus codec or pre-processed data - buffer directly
        _bufferAudioData(message);
      }
    } else if (message is String) {
      debugPrint('[WEBHOOK-SEND] Ignoring non-audio message (likely image chunk)');
    }
  }

  /// Process raw BLE packets and reassemble complete audio frames.
  /// BLE packets have a 3-byte header:
  /// - bytes 0-1: packet index (little-endian, wraps at 65535)
  /// - byte 2: internal frame index (0 = start of new frame, >0 = continuation)
  void _processRawBlePacket(List<int> value) {
    if (value.length < 3) {
      debugPrint('[WEBHOOK-FRAME] ⚠️ Packet too short: ${value.length} bytes');
      return;
    }

    int index = value[0] + (value[1] << 8); // packet index (little-endian)
    int internal = value[2]; // internal frame index
    List<int> content = value.sublist(3); // audio data

    // Start of a new frame when we're not tracking anything
    if (_lastPacketIndex == -1 && internal == 0) {
      _lastPacketIndex = index;
      _lastFrameId = internal;
      _pendingFrame = List<int>.from(content);
      return;
    }

    // Waiting for frame start - ignore continuations
    if (_lastPacketIndex == -1) {
      return;
    }

    // Check for packet loss or out-of-order packets
    // Handle packet index wraparound (65535 -> 0)
    int expectedIndex = (_lastPacketIndex + 1) & 0xFFFF;
    bool indexOk = index == expectedIndex;
    bool internalOk = internal == 0 || internal == _lastFrameId + 1;

    if (!indexOk || !internalOk) {
      debugPrint('[WEBHOOK-FRAME] ⚠️ Lost packet: expected idx=$expectedIndex got=$index, expected internal=${_lastFrameId + 1} got=$internal');
      _lastPacketIndex = -1;
      _pendingFrame = [];
      _framesLost++;

      // If this is a new frame start, begin tracking it
      if (internal == 0) {
        _lastPacketIndex = index;
        _lastFrameId = internal;
        _pendingFrame = List<int>.from(content);
      }
      return;
    }

    // Start of a new frame (previous frame complete)
    if (internal == 0) {
      // Process the completed frame
      if (_pendingFrame.isNotEmpty) {
        _framesReceived++;
        _processCompleteOpusFrame(_pendingFrame);
      }
      // Start new frame
      _pendingFrame = List<int>.from(content);
      _lastFrameId = internal;
      _lastPacketIndex = index;
      return;
    }

    // Continue current frame
    _pendingFrame.addAll(content);
    _lastFrameId = internal;
    _lastPacketIndex = index;
  }

  /// Process a complete Opus frame - decode to PCM and add to buffer
  void _processCompleteOpusFrame(List<int> frame) {
    if (frame.isEmpty) return;

    if (_opusDecoder != null) {
      try {
        final decodedSamples = _opusDecoder!.decode(input: Uint8List.fromList(frame));
        final pcmBytes = WavBytesUtil.convertToLittleEndianBytes(decodedSamples.toList());

        if (_framesReceived % 100 == 1) {
          // Log every 100th frame to reduce noise
          debugPrint('[WEBHOOK-FRAME] 🔊 Decoded ${frame.length} Opus bytes → ${decodedSamples.length} samples → ${pcmBytes.length} PCM bytes (frames: $_framesReceived, lost: $_framesLost)');
        }

        _bufferAudioData(pcmBytes.toList());
      } catch (e) {
        Logger.error('Failed to decode Opus frame: $e');
        debugPrint('[WEBHOOK-FRAME] ❌ Opus decode failed for ${frame.length} bytes - SKIPPING FRAME');
      }
    } else {
      // No decoder - buffer raw frame (shouldn't happen for Opus)
      _bufferAudioData(frame);
    }
  }

  /// Buffer decoded audio data and manage the batch timer
  void _bufferAudioData(List<int> audioData) {
    _audioBuffer.addAll(audioData);

    if (_batchTimer == null) {
      debugPrint('[WEBHOOK-SEND] ⏱️ Starting batch timer for ${_batchDelay}s (buffer: ${_audioBuffer.length} bytes)');
      _batchTimer = Timer(Duration(seconds: _batchDelay), () async {
        debugPrint('[WEBHOOK-SEND] ⏰ Batch timeout - flushing ${_audioBuffer.length} bytes');
        _batchTimer = null;
        await _flushBuffer();
      });
    }
  }

  Future _flushBuffer({bool forceFlush = true}) async {
    if (_audioBuffer.isEmpty) {
      debugPrint('[WEBHOOK] 📭 Buffer is empty, nothing to flush');
      return;
    }

    // Enforce minimum batch size (unless forced)
    if (!forceFlush && _audioBuffer.length < _minBatchSize) {
      final secondsBuffered = (_audioBuffer.length / (sampleRate * 2)).toStringAsFixed(1);
      final minSeconds = (_minBatchSize / (sampleRate * 2)).toStringAsFixed(0);
      debugPrint('[WEBHOOK] ⏸️ Buffer too small: ${_audioBuffer.length} bytes (${secondsBuffered}s) < $_minBatchSize bytes (${minSeconds}s) - waiting for more data');
      return;
    }

    final bufferSize = _audioBuffer.length;
    final secondsOfAudio = (bufferSize / (sampleRate * 2)).toStringAsFixed(2);

    final bytesToSend = List<int>.from(_audioBuffer);
    _audioBuffer.clear();

    debugPrint('[WEBHOOK] 📤 Flushing ${bytesToSend.length} bytes (${secondsOfAudio}s of audio at ${sampleRate}Hz PCM16)');
    await _sendToWebhook(bytesToSend);
  }

  Future flushImmediately() async {
    _batchTimer?.cancel();
    _batchTimer = null;
    await _flushBuffer(forceFlush: true);
  }

  Future _sendToWebhook(List<int> audioBytes) async {
    final webhookUrl = SharedPreferencesUtil().webhookAudioBytes;

    if (webhookUrl.isEmpty) {
      debugPrint('[WEBHOOK] No webhook URL configured');
      return;
    }

    try {
      var uid = SharedPreferencesUtil().uid;

      // Fallback to device name if no user UID is available
      if (uid.isEmpty) {
        uid = SharedPreferencesUtil().deviceName;
        if (uid.isEmpty) {
          uid = 'webhook-device';
        }
        debugPrint('[WEBHOOK] Using fallback UID: $uid');
      }

      // If we decoded Opus to PCM, report codec as pcm16
      final effectiveCodec = codec.isOpusSupported() ? 'pcm16' : codec.toString().split('.').last;
      final durationSeconds = (audioBytes.length / (sampleRate * 2)).toStringAsFixed(2);
      final url = '$webhookUrl?uid=$uid&sample_rate=$sampleRate';

      debugPrint('[WEBHOOK] 🌐 Sending to webhook:');
      debugPrint('[WEBHOOK]   URL: $url');
      debugPrint('[WEBHOOK]   Codec: $effectiveCodec');
      debugPrint('[WEBHOOK]   Size: ${audioBytes.length} bytes');
      debugPrint('[WEBHOOK]   Duration: ${durationSeconds}s');
      debugPrint('[WEBHOOK]   Sample Rate: ${sampleRate}Hz');
      debugPrint('[WEBHOOK]   Format: PCM16 little-endian');

      final response = await http.post(
        Uri.parse(url),
        headers: {'Content-Type': 'application/octet-stream'},
        body: audioBytes,
      ).timeout(const Duration(seconds: 30));

      debugPrint('[WEBHOOK] Response: ${response.statusCode}');

      if (response.statusCode >= 200 && response.statusCode < 300) {
        debugPrint('[WEBHOOK] ✅ Successfully sent audio bytes (${response.statusCode})');

        final payload = {
          'audio_bytes': '[${audioBytes.length} raw bytes]',
          'timestamp': DateTime.now().toIso8601String(),
          'uid': uid,
          'sample_rate': sampleRate,
          'codec': effectiveCodec,
          'language': language,
          'duration_seconds': _batchDelay,
        };

        if (onWebhookPayloadCapture != null) {
          onWebhookPayloadCapture!(payload);
        }

        if (onWebhookCalled != null) {
          onWebhookCalled!();
        }
      } else {
        final errorMsg = 'Webhook failed with status: ${response.statusCode}';
        debugPrint('[WEBHOOK] ❌ $errorMsg');
        debugPrint('[WEBHOOK] Response body: ${response.body}');
        _notifyWebhookError(errorMsg);
      }
    } catch (e) {
      final errorMsg = 'Error sending to webhook: $e';
      debugPrint('[WEBHOOK] ❌ $errorMsg');
      _notifyWebhookError(errorMsg);
    }
  }

  void _notifyWebhookError(String error) {
    if (onWebhookError != null) {
      onWebhookError!(error);
    }

    _listeners.forEach((k, v) {
      v.onError(error);
    });

    NotificationService.instance.createNotification(
      notificationId: 4,
      title: 'Webhook Connection Failed',
      body: 'Unable to send audio to your webhook. Please check your webhook URL in developer settings.',
    );
  }

  void _notifyConnected() {
    _listeners.forEach((k, v) {
      v.onConnected();
    });
  }

  int getPendingBufferSize() => _audioBuffer.length;

  String? getConnectionUrl() => null;

  int getKeepAliveInterval() => _keepAliveInterval;

  @override
  void onClosed([int? closeCode]) {}

  @override
  void onError(Object err, StackTrace trace) {}

  @override
  void onMessage(event) {}

  @override
  void onInternetConnectionFailed() {}

  @override
  void onMaxRetriesReach() {}

  @override
  void onConnected() {}
}
