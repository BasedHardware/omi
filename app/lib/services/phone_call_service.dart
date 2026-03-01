import 'dart:async';

import 'package:flutter/services.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/utils/logger.dart';

/// Native method channel bridge for phone call operations.
/// Communicates with iOS (Swift) and Android (Kotlin) native layers
/// for Twilio Voice SDK, CallKit, and audio capture.
class PhoneCallService {
  static const MethodChannel _methodChannel = MethodChannel('com.omi/phone_calls');
  static const EventChannel _eventChannel = EventChannel('com.omi/phone_calls/events');

  StreamSubscription? _eventSubscription;
  Function(PhoneCallState state)? onCallStateChanged;
  Function(Uint8List audioData, int channel)? onAudioData;

  PhoneCallService();

  /// Initialize the native Twilio SDK with an access token.
  Future<bool> initialize(String accessToken) async {
    try {
      final result = await _methodChannel.invokeMethod<bool>('initialize', {
        'accessToken': accessToken,
      });
      return result ?? false;
    } catch (e) {
      Logger.error('PhoneCallService: initialize error: $e');
      return false;
    }
  }

  /// Make an outbound call via Twilio Voice SDK.
  Future<bool> makeCall({
    required String phoneNumber,
    required String callId,
    String? contactName,
  }) async {
    try {
      final result = await _methodChannel.invokeMethod<bool>('makeCall', {
        'phoneNumber': phoneNumber,
        'callId': callId,
        'contactName': contactName,
      });
      return result ?? false;
    } catch (e, stackTrace) {
      Logger.error('PhoneCallService: makeCall error: $e\n$stackTrace');
      return false;
    }
  }

  /// End the current call.
  Future<void> endCall() async {
    try {
      await _methodChannel.invokeMethod('endCall');
    } catch (e) {
      Logger.error('PhoneCallService: endCall error: $e');
    }
  }

  /// Toggle mute on the current call.
  Future<void> toggleMute(bool muted) async {
    try {
      await _methodChannel.invokeMethod('toggleMute', {'muted': muted});
    } catch (e) {
      Logger.error('PhoneCallService: toggleMute error: $e');
    }
  }

  /// Toggle speaker on the current call.
  Future<void> toggleSpeaker(bool speakerOn) async {
    try {
      await _methodChannel.invokeMethod('toggleSpeaker', {'speakerOn': speakerOn});
    } catch (e) {
      Logger.error('PhoneCallService: toggleSpeaker error: $e');
    }
  }

  /// Start listening for call events from native side.
  void startListening() {
    _eventSubscription = _eventChannel.receiveBroadcastStream().listen(
      (event) {
        if (event is Map) {
          final type = event['type'] as String?;
          if (type == 'callStateChanged') {
            final stateStr = event['state'] as String?;
            if (stateStr != null && onCallStateChanged != null) {
              final state = _parseCallState(stateStr);
              onCallStateChanged!(state);
            }
          } else if (type == 'audioData') {
            final data = event['data'] as Uint8List?;
            final channel = event['channel'] as int?;
            if (data != null && channel != null && onAudioData != null) {
              onAudioData!(data, channel);
            }
          }
        }
      },
      onError: (error) {
        Logger.error('PhoneCallService: event stream error: $error');
      },
    );
  }

  /// Stop listening for call events.
  void stopListening() {
    _eventSubscription?.cancel();
    _eventSubscription = null;
  }

  PhoneCallState _parseCallState(String state) {
    switch (state) {
      case 'connecting':
        return PhoneCallState.connecting;
      case 'ringing':
        return PhoneCallState.ringing;
      case 'active':
        return PhoneCallState.active;
      case 'ended':
        return PhoneCallState.ended;
      case 'failed':
        return PhoneCallState.failed;
      default:
        return PhoneCallState.idle;
    }
  }

  void dispose() {
    stopListening();
  }
}
