import 'package:flutter/services.dart';
import 'dart:async';
import 'dart:typed_data';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/services/logger_service.dart';

class WatchManager {
  static const MethodChannel _channel = MethodChannel('com.friend.watch');
  static final WatchManager _instance = WatchManager._internal();
  final _logger = LoggerService();

  factory WatchManager() => _instance;
  WatchManager._internal();

  bool _isInitialized = false;
  CaptureProvider? _captureProvider;

  void setCaptureProvider(CaptureProvider provider) {
    _captureProvider = provider;
  }

  Future<void> initialize() async {
    if (_isInitialized) return;
    _channel.setMethodCallHandler(_handleMethodCall);
    _isInitialized = true;
    _logger.log('WatchManager initialized');
  }

  Future<dynamic> _handleMethodCall(MethodCall call) async {
    switch (call.method) {
      case 'audioDataReceived':
        if (call.arguments is Uint8List) {
          await _processAudioData(call.arguments as Uint8List);
        }
        break;
      case 'recordingStatus':
        if (call.arguments is bool) {
          final isRecording = call.arguments as bool;
          if (isRecording) {
            _captureProvider?.updateRecordingState(RecordingState.record);
          } else {
            _captureProvider?.updateRecordingState(RecordingState.stop);
          }
        }
        break;
    }
  }

  Future<void> _processAudioData(Uint8List audioData) async {
    try {
      if (_captureProvider == null) {
        _logger.error('CaptureProvider not set');
        return;
      }

      final samples = _convertToFloat32(audioData);
      await _captureProvider?.processAudioData(samples);
    } catch (e, stackTrace) {
      _logger.error('Error processing watch audio: $e\n$stackTrace');
    }
  }

  List<double> _convertToFloat32(Uint8List audioData) {
    final Int16List int16List = audioData.buffer.asInt16List();
    return List<double>.generate(
      int16List.length,
      (i) => int16List[i] / 32768.0,
    );
  }

  void dispose() {
    _isInitialized = false;
    _captureProvider = null;
    _logger.log('WatchManager disposed');
  }
}
