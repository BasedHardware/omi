import 'package:flutter/services.dart';
import 'dart:async';
import 'dart:typed_data';
import 'package:friend_private/providers/capture_provider.dart';
import 'package:friend_private/services/wals.dart';
import 'package:friend_private/services/services.dart';
import 'package:friend_private/utils/enums.dart';

class WatchManager {
  static const MethodChannel _channel = MethodChannel('com.friend.watch');
  static final WatchManager _instance = WatchManager._internal();

  factory WatchManager() => _instance;
  WatchManager._internal();

  bool _isInitialized = false;
  CaptureProvider? _captureProvider;
  IWalService get _wal => ServiceManager.instance().wal;

  bool _isWatchConnected = false;
  bool get isWatchConnected => _isWatchConnected;

  final _watchConnectionController = StreamController<bool>.broadcast();
  Stream<bool> get watchConnectionStream => _watchConnectionController.stream;

  void setCaptureProvider(CaptureProvider provider) {
    _captureProvider = provider;
  }

  Future<void> initialize() async {
    if (_isInitialized) return;
    _channel.setMethodCallHandler(_handleMethodCall);
    _isInitialized = true;
  }

  Future<dynamic> _handleMethodCall(MethodCall call) async {
    switch (call.method) {
      case 'audioDataReceived':
        if (call.arguments is Uint8List) {
          final audioData = call.arguments as Uint8List;
          await _processAudioData(audioData);
        }
        break;
      case 'recordingStatus':
        if (call.arguments is bool) {
          final isRecording = call.arguments as bool;
          if (isRecording) {
            _captureProvider?.updateRecordingState(RecordingState.record);
            _captureProvider?.updateRecordingSource(RecordingSource.watch);
          } else {
            _captureProvider?.updateRecordingState(RecordingState.stop);
          }
        }
        break;
      case 'watchConnectionChanged':
        _isWatchConnected = call.arguments as bool;
        _watchConnectionController.add(_isWatchConnected);
        break;
    }
  }

  Future<void> _processAudioData(Uint8List audioData) async {
    if (_captureProvider == null) return;

    // Send directly to socket like necklace/phone
    if (_captureProvider!.transcriptServiceReady) {
      _captureProvider!.processRawAudioData(audioData);
    }

    // Handle WAL if supported
    if (_captureProvider!.isWalSupported) {
      _wal.getSyncs().phone.onByteStream(audioData);
      _wal.getSyncs().phone.onBytesSync(audioData);
    }
  }

  void dispose() {
    _isInitialized = false;
    _captureProvider = null;
  }
}
