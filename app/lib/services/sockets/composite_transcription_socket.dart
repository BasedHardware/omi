import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/utils/debug_log_manager.dart';

class CompositeTranscriptionSocket implements IPureSocket {
  final IPureSocket primarySocket;
  final IPureSocket secondarySocket;

  final String? suggestedTranscriptType;
  final String? sttProvider;

  PureSocketStatus _status = PureSocketStatus.notConnected;
  IPureSocketListener? _listener;

  // Reconnection
  int _reconnectRetries = 0;
  Timer? _reconnectTimer;
  bool _stopped = false;  // Prevents reconnects after stop() is called
  static const int _maxReconnectRetries = 8;
  static const int _initialBackoffMs = 1000;
  static const double _backoffMultiplier = 1.5;

  late final _PrimarySocketListener _primaryListener;
  late final _SecondarySocketListener _secondaryListener;

  CompositeTranscriptionSocket({
    required this.primarySocket,
    required this.secondarySocket,
    this.suggestedTranscriptType = 'suggested_transcript',
    this.sttProvider,
  }) {
    _primaryListener = _PrimarySocketListener(this);
    _secondaryListener = _SecondarySocketListener(this);

    primarySocket.setListener(_primaryListener);
    secondarySocket.setListener(_secondaryListener);
  }

  @override
  PureSocketStatus get status => _status;

  @override
  void setListener(IPureSocketListener listener) {
    _listener = listener;
  }

  @override
  Future<bool> connect() async {
    if (_stopped) {
      CustomSttLogService.instance.info('Composite', 'Connect ignored - socket was stopped');
      return false;
    }
    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return false;
    }

    CustomSttLogService.instance.info('Composite', 'Connecting both sockets...');
    _status = PureSocketStatus.connecting;

    final results = await Future.wait([
      primarySocket.connect(),
      secondarySocket.connect(),
    ]);

    final primaryOk = results[0] && primarySocket.status == PureSocketStatus.connected;
    final secondaryOk = results[1] && secondarySocket.status == PureSocketStatus.connected;

    if (primaryOk && secondaryOk) {
      _status = PureSocketStatus.connected;
      _reconnectRetries = 0;
      CustomSttLogService.instance.info('Composite', 'Both sockets connected');
      DebugLogManager.logEvent('composite_socket_connected', {
        'primary_status': primarySocket.status.toString(),
        'secondary_status': secondarySocket.status.toString(),
      });
      onConnected();
      return true;
    }

    // Either failed - disconnect both and fail
    CustomSttLogService.instance.error(
      'Composite',
      'Connection failed - primary: $primaryOk, secondary: $secondaryOk',
    );
    DebugLogManager.logWarning('composite_socket_connect_failed', {
      'primary_ok': primaryOk,
      'secondary_ok': secondaryOk,
      'primary_status': primarySocket.status.toString(),
      'secondary_status': secondarySocket.status.toString(),
    });
    await _disconnectBothQuietly();
    _status = PureSocketStatus.notConnected;
    return false;
  }

  /// Disconnect both sockets without triggering composite callbacks
  Future<void> _disconnectBothQuietly() async {
    await Future.wait([
      primarySocket.disconnect(),
      secondarySocket.disconnect(),
    ]);
  }

  @override
  Future disconnect() async {
    CustomSttLogService.instance.info('Composite', 'Disconnecting...');
    DebugLogManager.logEvent('composite_socket_disconnecting', {});
    _cancelReconnect();

    await _disconnectBothQuietly();

    _status = PureSocketStatus.disconnected;
    onClosed();
  }

  @override
  Future stop() async {
    CustomSttLogService.instance.info('Composite', 'Stopping...');
    DebugLogManager.logEvent('composite_socket_stopping', {});
    _stopped = true;  // Prevent any further reconnect attempts
    _cancelReconnect();

    await Future.wait([
      primarySocket.stop(),
      secondarySocket.stop(),
    ]);

    _status = PureSocketStatus.disconnected;
  }

  void _cancelReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
  }

  /// Called when either socket closes unexpectedly
  void _onSocketClosed(String name, int? closeCode) {
    if (_status != PureSocketStatus.connected) {
      return; // Already handling disconnection
    }

    CustomSttLogService.instance.warning(
      'Composite',
      '$name socket closed (code: $closeCode), disconnecting composite',
    );
    DebugLogManager.logEvent('composite_socket_child_closed', {
      'child_socket': name,
      'close_code': closeCode ?? -1,
      'will_reconnect': !_stopped,
    });

    _status = PureSocketStatus.disconnected;
    _disconnectBothQuietly();
    onClosed(closeCode);
    _scheduleReconnect();
  }

  /// Called when either socket errors
  void _onSocketError(String name, Object err, StackTrace trace) {
    if (_status != PureSocketStatus.connected) {
      return;
    }

    CustomSttLogService.instance.error('Composite', '$name socket error: $err');
    DebugLogManager.logError(err, trace, 'composite_socket_child_error', {
      'child_socket': name,
    });

    _status = PureSocketStatus.disconnected;
    _disconnectBothQuietly();
    onError(err, trace);
    // Note: onClosed will likely follow, which will trigger reconnect
  }

  void _scheduleReconnect() {
    if (_stopped) {
      CustomSttLogService.instance.info('Composite', 'Reconnect skipped - socket was stopped');
      return;
    }
    if (_reconnectTimer != null) {
      return; // Already scheduled
    }
    if (_reconnectRetries >= _maxReconnectRetries) {
      CustomSttLogService.instance.warning(
        'Composite',
        'Max reconnect retries reached ($_maxReconnectRetries)',
      );
      DebugLogManager.logWarning('composite_socket_max_retries', {
        'max_retries': _maxReconnectRetries,
      });
      _listener?.onMaxRetriesReach();
      return;
    }

    final waitMs = (pow(_backoffMultiplier, _reconnectRetries) * _initialBackoffMs).toInt();
    CustomSttLogService.instance.info(
      'Composite',
      'Scheduling reconnect in ${waitMs}ms (attempt ${_reconnectRetries + 1}/$_maxReconnectRetries)',
    );

    DebugLogManager.logEvent('composite_socket_reconnect_scheduled', {
      'wait_ms': waitMs,
      'attempt': _reconnectRetries + 1,
      'max_retries': _maxReconnectRetries,
    });

    _reconnectTimer = Timer(Duration(milliseconds: waitMs), () async {
      _reconnectTimer = null;
      
      // Double-check stopped flag before attempting reconnect
      if (_stopped) {
        CustomSttLogService.instance.info('Composite', 'Reconnect timer fired but socket was stopped');
        return;
      }
      
      _reconnectRetries++;
      DebugLogManager.logEvent('composite_socket_reconnect_attempt', {
        'attempt': _reconnectRetries,
        'max_retries': _maxReconnectRetries,
      });
      final success = await connect();
      if (!success && !_stopped) {
        _scheduleReconnect();
      }
    });
  }

  @override
  void send(dynamic message) {
    if (_status != PureSocketStatus.connected) {
      return;
    }
    primarySocket.send(message);
    secondarySocket.send(message);
  }

  void _onPrimaryMessage(dynamic message) {
    _forwardAsSuggestedTranscript(message);
  }

  void _forwardAsSuggestedTranscript(dynamic message) {
    if (_status != PureSocketStatus.connected) {
      return;
    }

    try {
      dynamic segments = message is String ? jsonDecode(message) : message;

      final payload = <String, dynamic>{
        'type': suggestedTranscriptType,
        'segments': segments,
      };

      if (sttProvider != null) {
        payload['stt_provider'] = sttProvider;
      }

      secondarySocket.send(jsonEncode(payload));
    } catch (e) {
      CustomSttLogService.instance.error('Composite', 'Error forwarding transcript: $e');
    }
  }

  void _onSecondaryMessage(dynamic message) {
    onMessage(message);
  }

  @override
  void onConnected() {
    _listener?.onConnected();
  }

  @override
  void onMessage(dynamic message) {
    _listener?.onMessage(message);
  }

  @override
  void onClosed([int? closeCode]) {
    _listener?.onClosed(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    _listener?.onError(err, trace);
  }

  @override
  void onConnectionStateChanged(bool isConnected) {
    primarySocket.onConnectionStateChanged(isConnected);
    secondarySocket.onConnectionStateChanged(isConnected);
  }
}

// Simplified listeners - just delegate to composite
class _PrimarySocketListener implements IPureSocketListener {
  final CompositeTranscriptionSocket _composite;
  _PrimarySocketListener(this._composite);

  @override
  void onConnected() => debugPrint("[Composite/Primary] Connected");

  @override
  void onMessage(dynamic message) => _composite._onPrimaryMessage(message);

  @override
  void onClosed([int? closeCode]) => _composite._onSocketClosed('Primary', closeCode);

  @override
  void onError(Object err, StackTrace trace) => _composite._onSocketError('Primary', err, trace);

  @override
  void onInternetConnectionFailed() => debugPrint("[Composite/Primary] Internet failed");

  @override
  void onMaxRetriesReach() => debugPrint("[Composite/Primary] Max retries");
}

class _SecondarySocketListener implements IPureSocketListener {
  final CompositeTranscriptionSocket _composite;
  _SecondarySocketListener(this._composite);

  @override
  void onConnected() => debugPrint("[Composite/Secondary] Connected");

  @override
  void onMessage(dynamic message) => _composite._onSecondaryMessage(message);

  @override
  void onClosed([int? closeCode]) => _composite._onSocketClosed('Secondary', closeCode);

  @override
  void onError(Object err, StackTrace trace) => _composite._onSocketError('Secondary', err, trace);

  @override
  void onInternetConnectionFailed() => _composite._listener?.onInternetConnectionFailed();

  @override
  void onMaxRetriesReach() {} // Composite handles its own retries
}

