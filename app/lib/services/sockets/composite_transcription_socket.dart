import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/services/sockets/pure_socket.dart';
import 'package:omi/services/custom_stt_log_service.dart';

class CompositeTranscriptionSocket implements IPureSocket {
  final IPureSocket primarySocket;
  final IPureSocket secondarySocket;

  final String? suggestedTranscriptType;
  final String? sttProvider;

  PureSocketStatus _status = PureSocketStatus.notConnected;
  IPureSocketListener? _listener;

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
    if (_status == PureSocketStatus.connecting || _status == PureSocketStatus.connected) {
      return false;
    }

    CustomSttLogService.instance.info('Composite', 'Connecting both sockets...');
    _status = PureSocketStatus.connecting;

    final results = await Future.wait([
      primarySocket.connect(),
      secondarySocket.connect(),
    ]);

    final primaryConnected = results[0];
    final secondaryConnected = results[1];

    if (primaryConnected && secondaryConnected) {
      _status = PureSocketStatus.connected;
      CustomSttLogService.instance.info('Composite', 'Both sockets connected');
      onConnected();
      return true;
    }

    if (!secondaryConnected) {
      CustomSttLogService.instance.error('Composite', 'Secondary socket (Omi backend) failed to connect');
      _status = PureSocketStatus.notConnected;
      if (primaryConnected) {
        await primarySocket.disconnect();
      }
      return false;
    }

    if (!primaryConnected) {
      CustomSttLogService.instance.warning('Composite', 'Primary socket (custom STT) failed, continuing with secondary only');
      _status = PureSocketStatus.connected;
      onConnected();
      return true;
    }

    return false;
  }

  @override
  Future disconnect() async {
    CustomSttLogService.instance.info('Composite', 'Disconnecting...');

    await Future.wait([
      primarySocket.disconnect(),
      secondarySocket.disconnect(),
    ]);

    _status = PureSocketStatus.disconnected;
    onClosed();
  }

  @override
  Future stop() async {
    CustomSttLogService.instance.info('Composite', 'Stopping...');

    await Future.wait([
      primarySocket.stop(),
      secondarySocket.stop(),
    ]);

    _status = PureSocketStatus.disconnected;
  }

  @override
  void send(dynamic message) {
    primarySocket.send(message);
    secondarySocket.send(message);
  }

  void _onPrimaryTranscript(dynamic message) {
    _forwardSuggestedTranscript(message);
  }

  void _forwardSuggestedTranscript(dynamic message) {
    try {
      dynamic segments;
      if (message is String) {
        segments = jsonDecode(message);
      } else {
        segments = message;
      }

      final Map<String, dynamic> payload = {
        'type': suggestedTranscriptType,
        'segments': segments,
      };

      if (sttProvider != null) {
        payload['stt_provider'] = sttProvider;
      }

      final suggestedMessage = suggestedTranscriptType != null ? jsonEncode(payload) : message;

      secondarySocket.send(suggestedMessage);
    } catch (e) {
      CustomSttLogService.instance.error('Composite', 'Error forwarding transcript: $e');
    }
  }

  void _onSecondaryTranscript(dynamic message) {
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
    _status = PureSocketStatus.disconnected;
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

class _PrimarySocketListener implements IPureSocketListener {
  final CompositeTranscriptionSocket _composite;

  _PrimarySocketListener(this._composite);

  @override
  void onConnected() {
    debugPrint("[Composite/Primary] Connected");
  }

  @override
  void onMessage(dynamic message) {
    _composite._onPrimaryTranscript(message);
  }

  @override
  void onClosed([int? closeCode]) {
    debugPrint("[Composite/Primary] Closed with code: $closeCode");
  }

  @override
  void onError(Object err, StackTrace trace) {
    debugPrint("[Composite/Primary] Error: $err");
  }

  @override
  void onInternetConnectionFailed() {
    debugPrint("[Composite/Primary] Internet connection failed");
  }

  @override
  void onMaxRetriesReach() {
    debugPrint("[Composite/Primary] Max retries reached");
  }
}

class _SecondarySocketListener implements IPureSocketListener {
  final CompositeTranscriptionSocket _composite;

  _SecondarySocketListener(this._composite);

  @override
  void onConnected() {
    debugPrint("[Composite/Secondary] Connected");
  }

  @override
  void onMessage(dynamic message) {
    _composite._onSecondaryTranscript(message);
  }

  @override
  void onClosed([int? closeCode]) {
    debugPrint("[Composite/Secondary] Closed with code: $closeCode");
    _composite.onClosed(closeCode);
  }

  @override
  void onError(Object err, StackTrace trace) {
    debugPrint("[Composite/Secondary] Error: $err");
    _composite.onError(err, trace);
  }

  @override
  void onInternetConnectionFailed() {
    debugPrint("[Composite/Secondary] Internet connection failed");
    _composite._listener?.onInternetConnectionFailed();
  }

  @override
  void onMaxRetriesReach() {
    debugPrint("[Composite/Secondary] Max retries reached");
    _composite._listener?.onMaxRetriesReach();
  }
}

