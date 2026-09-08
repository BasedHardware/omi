import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/models/audio_route.dart';
import 'package:omi/utils/logger.dart';

/// Native method channel bridge for phone call operations.
/// Communicates with iOS (Swift) and Android (Kotlin) native layers
/// for Twilio Voice SDK, CallKit, and audio capture.
///
/// The event stream carries live call audio (100 buffers/sec across two
/// channels). A single malformed event must never end the subscription:
/// audio coercion failures are counted and dropped, and an error/done from
/// the platform side triggers a resubscribe while [startListening] is active.
class PhoneCallService {
  static const MethodChannel _methodChannel = MethodChannel('com.omi/phone_calls');
  static const EventChannel _eventChannel = EventChannel('com.omi/phone_calls/events');

  StreamSubscription? _eventSubscription;
  bool _listening = false;
  int _resubscribeDelayMs = 100;
  Timer? _resubscribeTimer;
  Function(PhoneCallState state)? onCallStateChanged;
  Function(Uint8List audioData, int channel)? onAudioData;
  Function(PhoneCallError error)? onError;
  Function(bool muted)? onMuteConfirmed;
  Function(bool speakerOn)? onSpeakerConfirmed;

  /// Events dropped because a field could not be coerced since the last
  /// [resetEventStats]. Counts only; never carries payload.
  int eventChannelErrors = 0;

  /// Events delivered only after coercing `data`/`channel` types: counted
  /// once per delivered event (never per coerced field), and never for
  /// events that were dropped — those are [eventChannelErrors].
  int eventChannelCoerced = 0;

  /// Whether the event being dispatched needed any field coercion. Set by
  /// the coerce helpers and consumed once per event, only on delivery.
  bool _eventNeededCoercion = false;

  PhoneCallService();

  /// Initialize the native Twilio SDK with an access token.
  Future<bool> initialize(String accessToken) async {
    try {
      final result = await _methodChannel.invokeMethod<bool>('initialize', {'accessToken': accessToken});
      return result ?? false;
    } catch (e) {
      Logger.error('PhoneCallService: initialize error: $e');
      return false;
    }
  }

  /// Make an outbound call via Twilio Voice SDK.
  Future<bool> makeCall({required String phoneNumber, required String callId, String? contactName}) async {
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

  /// Toggle mute on the current call. State update comes via onMuteConfirmed callback.
  Future<void> toggleMute(bool muted) async {
    try {
      await _methodChannel.invokeMethod('toggleMute', {'muted': muted});
    } catch (e) {
      Logger.error('PhoneCallService: toggleMute error: $e');
    }
  }

  /// Toggle speaker on the current call. State update comes via onSpeakerConfirmed callback.
  Future<void> toggleSpeaker(bool speakerOn) async {
    try {
      await _methodChannel.invokeMethod('toggleSpeaker', {'speakerOn': speakerOn});
    } catch (e) {
      Logger.error('PhoneCallService: toggleSpeaker error: $e');
    }
  }

  /// Send DTMF tones during an active call.
  Future<void> sendDtmf(String digits) async {
    try {
      await _methodChannel.invokeMethod('sendDtmf', {'digits': digits});
    } catch (e) {
      Logger.error('PhoneCallService: sendDtmf error: $e');
    }
  }

  /// Start listening for call events from native side.
  ///
  /// The subscription survives malformed events and resubscribes after a
  /// platform-side error or done until [stopListening] cancels it. Calling this
  /// again replaces any existing subscription (never duplicates) and resets the
  /// resubscribe backoff.
  void startListening() {
    _listening = true;
    _resubscribeDelayMs = 100;
    _resubscribeTimer?.cancel();
    _resubscribeTimer = null;
    _eventSubscription?.cancel();
    _eventSubscription = _eventChannel.receiveBroadcastStream().listen(
      (event) => _handleEvent(event),
      onError: (error) {
        Logger.error('PhoneCallService: event stream error: $error');
        _scheduleResubscribe();
      },
      onDone: _scheduleResubscribe,
    );
  }

  /// Stop listening for call events and cancel any pending resubscribe.
  void stopListening() {
    _listening = false;
    _resubscribeTimer?.cancel();
    _resubscribeTimer = null;
    _eventSubscription?.cancel();
    _eventSubscription = null;
  }

  /// Reset per-call event counters. Called when a call session starts.
  void resetEventStats() {
    eventChannelErrors = 0;
    eventChannelCoerced = 0;
    _resubscribeDelayMs = 100;
  }

  /// Dispatch one raw platform event through the production path.
  @visibleForTesting
  void handleEventForTesting(Object? event) => _handleEvent(event);

  /// Exactly one resubscribe may be pending at a time; a second error/done
  /// before the timer fires replaces the timer instead of stacking a second
  /// subscription attempt on top of it.
  void _scheduleResubscribe() {
    if (!_listening) return;
    _resubscribeTimer?.cancel();
    var delay = Duration(milliseconds: _resubscribeDelayMs);
    _resubscribeDelayMs = (_resubscribeDelayMs * 2).clamp(100, 2000);
    _resubscribeTimer = Timer(delay, () {
      _resubscribeTimer = null;
      if (_listening) {
        Logger.info('PhoneCallService: resubscribing to event stream');
        startListening();
      }
    });
  }

  void _handleEvent(Object? event) {
    try {
      _dispatchEvent(event);
    } catch (error, stackTrace) {
      eventChannelErrors++;
      Logger.error('PhoneCallService: event dispatch failed: $error\n$stackTrace');
    }
  }

  void _dispatchEvent(Object? event) {
    if (event is! Map) return;
    final type = event['type'] as String?;
    if (type == 'callStateChanged') {
      final stateStr = event['state'] as String?;
      if (stateStr != null && onCallStateChanged != null) {
        final state = _parseCallState(stateStr);
        onCallStateChanged!(state);
      }
    } else if (type == 'audioData') {
      _eventNeededCoercion = false;
      final data = _coerceAudioData(event['data']);
      final channel = _coerceChannel(event['channel']);
      if (data != null && channel != null) {
        // Count once per successfully delivered event, not once per coerced
        // field; dropped events are eventChannelErrors and must not inflate
        // this metric. Incremented after delivery so a throwing callback
        // counts as an error, not a coerced delivery.
        onAudioData?.call(data, channel);
        if (_eventNeededCoercion) eventChannelCoerced++;
      } else {
        eventChannelErrors++;
        Logger.error(
          'PhoneCallService: dropped audio event (data=${data == null ? "invalid" : "ok"}, channel=${channel == null ? "invalid" : "ok"})',
        );
      }
    } else if (type == 'error') {
      final error = PhoneCallError.fromEvent(event);
      Logger.error('PhoneCallService: native error: $error');
      onError?.call(error);
    } else if (type == 'muteConfirmed') {
      final muted = event['muted'] as bool? ?? false;
      onMuteConfirmed?.call(muted);
    } else if (type == 'speakerConfirmed') {
      final speakerOn = event['speakerOn'] as bool? ?? false;
      onSpeakerConfirmed?.call(speakerOn);
    }
  }

  /// Native sides send `data` as Uint8List (iOS FlutterStandardTypedData,
  /// Android ByteArray), but any List<int> shape is still valid audio —
  /// coerce instead of dropping the frame.
  Uint8List? _coerceAudioData(Object? value) {
    if (value is Uint8List) return value;
    if (value is Int8List) {
      _eventNeededCoercion = true;
      var result = Uint8List(value.length);
      for (var i = 0; i < value.length; i++) {
        result[i] = value[i] & 0xff;
      }
      return result;
    }
    if (value is List<int>) {
      _eventNeededCoercion = true;
      try {
        return Uint8List.fromList(value);
      } catch (_) {
        return null;
      }
    }
    // The standard codec decodes a generic int list as List<dynamic>, which is
    // still valid audio bytes.
    if (value is List) {
      _eventNeededCoercion = true;
      var result = Uint8List(value.length);
      for (var i = 0; i < value.length; i++) {
        var element = value[i];
        if (element is! int || element < 0 || element > 255) return null;
        result[i] = element;
      }
      return result;
    }
    return null;
  }

  int? _coerceChannel(Object? value) {
    if (value is int) return value;
    if (value is num) {
      _eventNeededCoercion = true;
      return value.toInt();
    }
    if (value is String) {
      final parsed = int.tryParse(value);
      if (parsed != null) {
        _eventNeededCoercion = true;
        return parsed;
      }
    }
    return null;
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

  /// Get available audio output routes (iPhone, Speaker, AirPods, Bluetooth, etc.)
  Future<List<AudioRoute>> getAudioRoutes() async {
    try {
      final result = await _methodChannel.invokeMethod<List>('getAudioRoutes');
      if (result == null) return [];
      return result.map((r) => AudioRoute.fromMap(Map<String, dynamic>.from(r as Map))).toList();
    } catch (e) {
      Logger.error('PhoneCallService: getAudioRoutes error: $e');
      return [];
    }
  }

  /// Select a specific audio output route by ID.
  Future<bool> selectAudioRoute(String routeId) async {
    try {
      final result = await _methodChannel.invokeMethod<bool>('selectAudioRoute', {'routeId': routeId});
      return result ?? false;
    } catch (e) {
      Logger.error('PhoneCallService: selectAudioRoute error: $e');
      return false;
    }
  }

  /// Check if CallKit is available (false in China).
  Future<bool> isCallKitAvailable() async {
    try {
      final result = await _methodChannel.invokeMethod<bool>('isCallKitAvailable');
      return result ?? true;
    } catch (e) {
      return true; // Default to available
    }
  }

  void dispose() {
    stopListening();
  }
}
