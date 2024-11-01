import 'package:flutter/services.dart';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/utils/logger.dart';
import 'package:friend_private/services/wals.dart';
import 'package:friend_private/services/services.dart';

class WatchManager {
  static const MethodChannel _channel = MethodChannel('com.friend.watch');
  static final WatchManager _instance = WatchManager._internal();
  final _logger = Logger.instance;

  CaptureProvider? _captureProvider;
  bool _isRecording = false;
  bool get isRecording => _isRecording;

  WatchManager._internal();
  factory WatchManager() => _instance;

  Future<bool> isWatchAvailable() async {
    try {
      final result = await _channel.invokeMethod<bool>('isWatchAvailable') ?? false;
      return result;
    } catch (e) {
      _logger.error('Error checking watch availability', e);
      return false;
    }
  }

  Future<void> startRecording() async {
    try {
      await _channel.invokeMethod('startRecording');
      _isRecording = true;
      if (_captureProvider != null) {
        _captureProvider!.updateRecordingState(
          _isRecording ? RecordingState.record : RecordingState.stop
        );
        _captureProvider!.updateRecordingSource(RecordingSource.watch);
      }
    } catch (e) {
      _logger.error('Error starting watch recording', e);
    }
  }

  Future<void> stopRecording() async {
    try {
      await _channel.invokeMethod('stopRecording');
      _isRecording = false;
      if (_captureProvider != null) {
        _captureProvider!.updateRecordingState(RecordingState.stop);
      }
    } catch (e) {
      _logger.error('Error stopping watch recording', e);
    }
  }

  Future<void> handleAudioData(Uint8List audioData) async {
    try {
      await _captureProvider?.processRawAudioData(audioData);
    } catch (e) {
      _logger.error('Error processing watch audio data', e);
    }
  }

  void setCaptureProvider(CaptureProvider provider) {
    _captureProvider = provider;
  }

  void initialize() {
    // Add any initialization logic
  }

  void dispose() {
    // Add cleanup logic
  }

  void _setupMethodCallHandler() {
    _channel.setMethodCallHandler((call) async {
      switch (call.method) {
        case 'onAudioData':
          final audioData = call.arguments as Uint8List;
          await handleAudioData(audioData);
          break;
      }
    });
  }
}
