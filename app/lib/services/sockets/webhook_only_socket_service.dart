import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/notifications.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/sockets/transcription_connection.dart';

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

    debugPrint('WebhookOnlySocketService: Batch delay=${_batchDelay}s, KeepAlive=${_keepAliveInterval}s');
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

    await _flushBuffer();

    _listeners.clear();
    _state = SocketServiceState.disconnected;

    if (reason != null) {
      debugPrint('WebhookOnlySocketService stopped: $reason');
    }
  }

  @override
  Future send(dynamic message) async {
    if (message is List<int>) {
      _audioBuffer.addAll(message);

      _batchTimer?.cancel();
      _batchTimer = Timer(Duration(seconds: _batchDelay), () async {
        await _flushBuffer();
      });
    } else if (message is String) {
      debugPrint('WebhookOnlySocketService: Ignoring non-audio message (likely image chunk)');
    }
  }

  Future _flushBuffer() async {
    if (_audioBuffer.isEmpty) return;

    final bytesToSend = List<int>.from(_audioBuffer);
    _audioBuffer.clear();

    await _sendToWebhook(bytesToSend);
  }

  Future flushImmediately() async {
    _batchTimer?.cancel();
    await _flushBuffer();
  }

  Future _sendToWebhook(List<int> audioBytes) async {
    final webhookUrl = SharedPreferencesUtil().webhookAudioBytes;

    if (webhookUrl.isEmpty) {
      debugPrint('WebhookOnlySocketService: No webhook URL configured');
      return;
    }

    try {
      final base64Audio = base64Encode(Uint8List.fromList(audioBytes));

      final payload = {
        'audio_bytes': base64Audio,
        'timestamp': DateTime.now().toIso8601String(),
        'uid': SharedPreferencesUtil().uid,
        'sample_rate': sampleRate,
        'codec': codec.toString().split('.').last,
        'language': language,
        'duration_seconds': _batchDelay,
      };

      if (onWebhookPayloadCapture != null) {
        onWebhookPayloadCapture!(payload);
      }

      debugPrint('WebhookOnlySocketService: Sending ${audioBytes.length} bytes to $webhookUrl');

      final response = await makeApiCall(
        url: webhookUrl,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(payload),
        method: 'POST',
      );

      if (response != null && response.statusCode >= 200 && response.statusCode < 300) {
        debugPrint('WebhookOnlySocketService: Successfully sent audio bytes (${response.statusCode})');
        if (onWebhookCalled != null) {
          onWebhookCalled!();
        }
      } else {
        final errorMsg = 'Webhook failed with status: ${response?.statusCode}';
        debugPrint('WebhookOnlySocketService: $errorMsg');
        _notifyWebhookError(errorMsg);
      }
    } catch (e) {
      final errorMsg = 'Error sending to webhook: $e';
      debugPrint('WebhookOnlySocketService: $errorMsg');
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
