import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import 'package:omi/utils/logger.dart';

class ClockSkewEvent {
  final String? serverTime;
  final String? clientTime;
  final int skewSeconds;
  final String? hint;

  const ClockSkewEvent({
    required this.serverTime,
    required this.clientTime,
    required this.skewSeconds,
    required this.hint,
  });

  int get skewMinutes {
    final minutes = (skewSeconds.abs() / 60).ceil();
    return minutes == 0 ? 1 : minutes;
  }
}

class ClockSkewDetector {
  static final ClockSkewDetector instance = ClockSkewDetector._();
  ClockSkewDetector._();

  static const Duration cooldown = Duration(seconds: 45);
  DateTime? _lastEmittedAt;

  final _controller = StreamController<ClockSkewEvent>.broadcast();
  Stream<ClockSkewEvent> get onClockSkew => _controller.stream;

  void checkResponse(http.Response response) {
    final event = parseResponse(response);
    if (event == null) return;

    Logger.warning(
      'Clock skew detected: skew_seconds=${event.skewSeconds}, '
      'server_time=${event.serverTime}, '
      'client_time=${event.clientTime}',
    );

    final now = DateTime.now();
    if (_lastEmittedAt != null && now.difference(_lastEmittedAt!) < cooldown) {
      return;
    }

    _lastEmittedAt = now;
    _controller.add(event);
  }

  @visibleForTesting
  void resetForTesting() {
    _lastEmittedAt = null;
  }

  @visibleForTesting
  void setLastEmittedAtForTesting(DateTime dt) {
    _lastEmittedAt = dt;
  }

  static ClockSkewEvent? parseResponse(http.Response response) {
    if (response.statusCode != 408 || response.body.isEmpty) {
      return null;
    }

    final contentType = response.headers['content-type']?.toLowerCase() ?? '';
    if (!contentType.contains('json')) {
      return null;
    }

    try {
      final dynamic decoded = jsonDecode(response.body);
      if (decoded is! Map) {
        return null;
      }
      final responseMap = decoded.map((key, value) => MapEntry(key.toString(), value));
      if (responseMap['error']?.toString() != 'clock_skew') {
        return null;
      }

      final skewSeconds = _parseInt(responseMap['skew_seconds']);
      if (skewSeconds == null) {
        return null;
      }

      return ClockSkewEvent(
        serverTime: responseMap['server_time']?.toString(),
        clientTime: responseMap['client_time']?.toString(),
        skewSeconds: skewSeconds,
        hint: responseMap['hint']?.toString(),
      );
    } catch (e) {
      Logger.debug('Failed to parse clock skew response: $e');
      return null;
    }
  }

  static int? _parseInt(dynamic value) {
    if (value is int) return value;
    if (value is num) return value.round();
    if (value is String) return int.tryParse(value);
    return null;
  }
}
