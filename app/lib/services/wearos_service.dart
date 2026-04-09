import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/services.dart';
import 'package:omi/utils/logger.dart';

/// Service that communicates with the native WearOS audio bridge.
///
/// Listens for audio data from the WearOS watch via an EventChannel and
/// provides control queries via a MethodChannel. Singleton pattern
/// matching other Omi services.
class WearOsService {
  static final WearOsService _instance = WearOsService._internal();
  factory WearOsService() => _instance;
  WearOsService._internal();

  static const String _audioChannelName = 'com.friend.ios/wearos_audio';
  static const String _controlChannelName = 'com.friend.ios/wearos_control';

  static const EventChannel _audioChannel = EventChannel(_audioChannelName);
  static const MethodChannel _controlChannel = MethodChannel(_controlChannelName);

  StreamSubscription? _audioSubscription;
  final StreamController<WearOsAudioEvent> _audioStreamController =
      StreamController<WearOsAudioEvent>.broadcast();
  final StreamController<WearOsConnectionEvent> _connectionStreamController =
      StreamController<WearOsConnectionEvent>.broadcast();

  bool _isListening = false;

  /// Stream of audio data events from the watch.
  Stream<WearOsAudioEvent> get audioStream => _audioStreamController.stream;

  /// Stream of connection state change events.
  Stream<WearOsConnectionEvent> get connectionStream =>
      _connectionStreamController.stream;

  /// Start listening for audio data from the watch.
  void startListening() {
    if (_isListening) return;
    _isListening = true;

    _audioSubscription = _audioChannel.receiveBroadcastStream().listen(
      (dynamic event) {
        if (event is Map) {
          _handleEvent(Map<String, dynamic>.from(event));
        }
      },
      onError: (dynamic error) {
        Logger.handle(
          error,
          StackTrace.current,
          message: 'WearOS audio stream error',
        );
      },
      onDone: () {
        _isListening = false;
      },
    );
  }

  /// Stop listening for audio data.
  void stopListening() {
    _audioSubscription?.cancel();
    _audioSubscription = null;
    _isListening = false;
  }

  /// Handle an event from the native EventChannel.
  void _handleEvent(Map<String, dynamic> event) {
    // Connection state change event
    if (event.containsKey('connectionState')) {
      final connected = event['connectionState'] as bool;
      final nodeId = event['nodeId'] as String? ?? '';
      final displayName = event['displayName'] as String? ?? '';
      _connectionStreamController.add(WearOsConnectionEvent(
        connected: connected,
        nodeId: nodeId,
        displayName: displayName,
      ));
      return;
    }

    // Audio data event
    if (event.containsKey('audioData')) {
      final audioData = event['audioData'];
      final Uint8List bytes;
      if (audioData is Uint8List) {
        bytes = audioData;
      } else if (audioData is List) {
        bytes = Uint8List.fromList(List<int>.from(audioData));
      } else {
        return;
      }

      final isFinal = event['isFinal'] as bool? ?? false;
      final segmentId = event['segmentId'] as String? ?? '';
      final confidence = (event['confidence'] as num?)?.toDouble() ?? 0.0;

      _audioStreamController.add(WearOsAudioEvent(
        audioData: bytes,
        isFinal: isFinal,
        segmentId: segmentId,
        confidence: confidence,
      ));
    }
  }

  /// Check if a WearOS watch is connected.
  Future<bool> isWatchConnected() async {
    try {
      final result = await _controlChannel.invokeMethod<bool>('isWatchConnected');
      return result ?? false;
    } on PlatformException catch (e) {
      Logger.handle(e, StackTrace.current, message: 'isWatchConnected failed');
      return false;
    }
  }

  /// Get device info for the connected watch.
  Future<Map<String, dynamic>> getWatchDeviceInfo() async {
    try {
      final result = await _controlChannel
          .invokeMapMethod<String, dynamic>('getWatchDeviceInfo');
      return result ?? {'deviceId': 'wearos-watch', 'deviceModel': 'WearOS Watch'};
    } on PlatformException catch (e) {
      Logger.handle(e, StackTrace.current, message: 'getWatchDeviceInfo failed');
      return {'deviceId': 'wearos-watch', 'deviceModel': 'WearOS Watch'};
    }
  }

  /// Dispose of resources.
  void dispose() {
    stopListening();
    _audioStreamController.close();
    _connectionStreamController.close();
  }
}

/// Audio data event received from the WearOS watch.
class WearOsAudioEvent {
  final Uint8List audioData;
  final bool isFinal;
  final String segmentId;
  final double confidence;

  WearOsAudioEvent({
    required this.audioData,
    required this.isFinal,
    required this.segmentId,
    required this.confidence,
  });
}

/// Connection state change event from the WearOS watch.
class WearOsConnectionEvent {
  final bool connected;
  final String nodeId;
  final String displayName;

  WearOsConnectionEvent({
    required this.connected,
    required this.nodeId,
    required this.displayName,
  });
}
