import 'dart:async';

import 'package:flutter/services.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/services/wals.dart';
import 'package:friend_private/utils/enums.dart';

enum WatchConnectionState {
  disconnected,
  connecting,
  connected,
  error,
}

class WatchManager {

  factory WatchManager() => _instance;
  WatchManager._internal();
  static const MethodChannel _channel = MethodChannel('com.friend.watch');
  static final WatchManager _instance = WatchManager._internal();
  final LoggerService _logger = LoggerService();

  bool _isInitialized = false;
  CaptureProvider? _captureProvider;
  IWalService get _wal => ServiceManager.instance().wal;

  final StreamController<WatchConnectionState> _connectionStateController =
      StreamController<WatchConnectionState>.broadcast();
  Stream<WatchConnectionState> get connectionState => _connectionStateController.stream;
  WatchConnectionState _currentState = WatchConnectionState.disconnected;

  final StreamController<String> _errorController = StreamController<String>.broadcast();
  Stream<String> get errors => _errorController.stream;

  void setCaptureProvider(CaptureProvider provider) {
    _captureProvider = provider;
  }

  Future<void> initialize() async {
    if (_isInitialized) {
      return;
    }

    try {
      _connectionStateController.add(WatchConnectionState.connecting);

      await _channel.invokeMethod<void>('initializeWatchConnection');
      _channel.setMethodCallHandler(_handleMethodCall);

      _isInitialized = true;
      _connectionStateController.add(WatchConnectionState.connected);
      _logger.log('WatchManager initialized successfully');
    } catch (e, stackTrace) {
      _connectionStateController.add(WatchConnectionState.error);
      _errorController.add('Failed to initialize watch connection: $e');
      _logger.error('Watch initialization failed', e, stackTrace);
    }
  }

  Future<dynamic> _handleMethodCall(MethodCall call) async {
    try {
      switch (call.method) {
        case 'audioDataReceived':
          if (call.arguments is Uint8List) {
            await _processAudioData(call.arguments as Uint8List);
          }
          break;
        case 'watchConnectionStateChanged':
          _handleConnectionStateChange(call.arguments as String);
          break;
        case 'recordingStatus':
          _handleRecordingStatus(call.arguments as bool);
          break;
        case 'error':
          _handleError(call.arguments as String);
          break;
      }
    } catch (e, stackTrace) {
      _logger.error('Error handling method call: ${call.method}', e, stackTrace);
      _errorController.add('Error processing watch data: $e');
    }
  }

  void _handleConnectionStateChange(String state) {
    switch (state) {
      case 'connected':
        _currentState = WatchConnectionState.connected;
        break;
      case 'disconnected':
        _currentState = WatchConnectionState.disconnected;
        break;
      case 'error':
        _currentState = WatchConnectionState.error;
        break;
      default:
        _currentState = WatchConnectionState.disconnected;
    }
    _connectionStateController.add(_currentState);
  }

  void _handleRecordingStatus(bool isRecording) {
    if (_captureProvider == null) return;

    if (isRecording) {
      _captureProvider?.updateRecordingState(RecordingState.record);
      _captureProvider?.updateRecordingSource(RecordingSource.watch);
    } else {
      _captureProvider?.updateRecordingState(RecordingState.stop);
    }
  }

  void _handleError(String errorMessage) {
    _logger.error('Watch error: $errorMessage');
    _errorController.add(errorMessage);
  }

  Future<void> _processAudioData(Uint8List audioData) async {
    if (_captureProvider == null) {
      _logger.error('CaptureProvider not set');
      return;
    }

    if (_currentState != WatchConnectionState.connected) {
      _logger.error('Watch not connected, dropping audio data');
      return;
    }

    try {
      // Send directly to socket like necklace/phone
      if (_captureProvider!.transcriptServiceReady) {
        _captureProvider!.processRawAudioData(audioData);
      }

      // Handle WAL if supported
      if (_captureProvider!.isWalSupported) {
        _wal.getSyncs().phone.onByteStream(audioData);
        _wal.getSyncs().phone.onBytesSync(audioData);
      }
    } catch (e, stackTrace) {
      _logger.error('Error processing watch audio data', e, stackTrace);
      _errorController.add('Error processing audio: $e');
    }
  }

  Future<bool> isWatchAvailable() async {
    try {
      final bool available = await _channel.invokeMethod('isWatchAvailable');
      return available;
    } catch (e) {
      _logger.error('Error checking watch availability', e);
      return false;
    }
  }

  @override
  void dispose() {
    _isInitialized = false;
    _captureProvider = null;
    _connectionStateController.close();
    _errorController.close();
    _logger.log('WatchManager disposed');
	_watchConnectionController.close();
  }
}
