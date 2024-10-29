import 'package:flutter/services.dart';
import 'package:friend_private/services/logger_service.dart';
import 'package:friend_private/utils/enums.dart';
import 'package:friend_private/models/capture_provider.dart';
import 'package:friend_private/services/wal_service.dart';

class WatchManager {
  static const MethodChannel _channel = MethodChannel('com.friend.watch');
  static final WatchManager _instance = WatchManager._internal();
  final _logger = LoggerService();

  bool _isRecording = false;
  bool get isRecording => _isRecording;

  CaptureProvider? _captureProvider;

  final IWalService _walService;

  factory WatchManager() => _instance;
  WatchManager._internal() : _walService = ServiceManager.instance().wal {
    _setupMethodCallHandler();
  }

  void _setupMethodCallHandler() {
    _channel.setMethodCallHandler((call) async {
      switch (call.method) {
        case 'audioDataReceived':
          if (call.arguments is Uint8List) {
            await _handleAudioData(call.arguments as Uint8List);
          }
          break;
        case 'recordingStatus':
          _isRecording = call.arguments as bool;
          _notifyRecordingStateChanged();
          break;
        case 'walSyncStatus':
          // Handle WAL sync completion
          break;
      }
    });
  }

  Future<void> _handleAudioData(Uint8List audioData) async {
    try {
      if (_captureProvider?.transcriptServiceReady ?? false) {
        // Process audio through WAL if supported
        if (_captureProvider!.isWalSupported) {
          _walService.getSyncs().phone.onByteStream(audioData);
          _walService.getSyncs().phone.onBytesSync(audioData);
        }

        // Process through capture provider
        await _captureProvider?.processRawAudioData(audioData);
      }
    } catch (e) {
      _logger.error('Error processing watch audio data', e);
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

  Future<void> startRecording() async {
    try {
      await _channel.invokeMethod('startWatchRecording');
    } catch (e) {
      _logger.error('Error starting watch recording', e);
    }
  }

  Future<void> stopRecording() async {
    try {
      await _channel.invokeMethod('stopWatchRecording');
    } catch (e) {
      _logger.error('Error stopping watch recording', e);
    }
  }

  void _notifyRecordingStateChanged() {
    if (_captureProvider != null) {
      _captureProvider!.updateRecordingState(
        _isRecording ? RecordingState.record : RecordingState.stop
      );
      _captureProvider!.updateRecordingSource(RecordingSource.watch);
    }
  }

  void setCaptureProvider(CaptureProvider provider) {
    _captureProvider = provider;
  }
}
