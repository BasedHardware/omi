import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'package:omi/backend/http/api/phone_calls.dart' as api;
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/models/audio_route.dart';
import 'package:omi/services/phone_call_service.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/logger.dart';

enum TranscriptionStatus { idle, connecting, active, reconnecting, failed }

class PhoneCallProvider extends ChangeNotifier {
  final PhoneCallService _nativeService = PhoneCallService();

  // Call state
  PhoneCallState _callState = PhoneCallState.idle;
  PhoneCallState get callState => _callState;

  String? _currentCallId;
  String? get currentCallId => _currentCallId;

  String? _remoteNumber;
  String? get remoteNumber => _remoteNumber;

  String? _contactName;
  String? get contactName => _contactName;

  bool _isMuted = false;
  bool get isMuted => _isMuted;

  bool _isSpeakerOn = false;
  bool get isSpeakerOn => _isSpeakerOn;

  // Call duration
  DateTime? _callStartTime;
  Timer? _durationTimer;
  Duration _callDuration = Duration.zero;
  Duration get callDuration => _callDuration;

  // Real-time transcript segments
  final List<TranscriptSegment> _transcriptSegments = [];
  List<TranscriptSegment> get transcriptSegments => List.unmodifiable(_transcriptSegments);

  // Audio routes
  List<AudioRoute> _availableRoutes = [];
  List<AudioRoute> get availableRoutes => List.unmodifiable(_availableRoutes);
  AudioRoute? _selectedRoute;
  AudioRoute? get selectedRoute => _selectedRoute;

  // Transcription status
  TranscriptionStatus _transcriptionStatus = TranscriptionStatus.idle;
  TranscriptionStatus get transcriptionStatus => _transcriptionStatus;

  // Token refresh
  Timer? _tokenRefreshTimer;

  // WebSocket for transcription
  WebSocketChannel? _transcriptionSocket;
  int _wsReconnectAttempts = 0;
  Timer? _wsReconnectTimer;
  static const int _maxWsReconnectAttempts = 10;

  // Audio buffer during WS reconnect (~2s at 20ms per frame)
  final List<Uint8List> _audioBuffer = [];
  static const int _maxAudioBufferSize = 100;

  // Verified phone numbers
  List<VerifiedPhoneNumber> _verifiedNumbers = [];
  List<VerifiedPhoneNumber> get verifiedNumbers => _verifiedNumbers;

  // Loading states
  bool _isLoading = false;
  bool get isLoading => _isLoading;

  bool _numbersLoaded = false;
  bool get numbersLoaded => _numbersLoaded;

  String? _error;
  String? get error => _error;

  PhoneCallError? _lastError;
  PhoneCallError? get lastError => _lastError;

  Future<void>? _initialLoad;
  Future<void> get initialLoad => _initialLoad ?? Future.value();

  PhoneCallProvider() {
    _nativeService.onCallStateChanged = _onCallStateChanged;
    _nativeService.onAudioData = _onAudioData;
    _nativeService.onError = _onNativeError;
    _nativeService.onMuteConfirmed = _onMuteConfirmed;
    _nativeService.onSpeakerConfirmed = _onSpeakerConfirmed;
    _nativeService.startListening();
    _initialLoad = loadVerifiedNumbers();
  }

  // ************************************************
  // *********** PHONE NUMBER MANAGEMENT ************
  // ************************************************

  Future<void> loadVerifiedNumbers() async {
    try {
      _verifiedNumbers = await api.getVerifiedPhoneNumbers();
    } catch (e) {
      print('PhoneCallProvider: failed to load verified numbers: $e');
      _verifiedNumbers = [];
    } finally {
      _numbersLoaded = true;
      notifyListeners();
    }
  }

  String? _validationCode;
  String? get validationCode => _validationCode;

  String? _verificationStatus;
  String? get verificationStatus => _verificationStatus;

  Future<bool> startVerification(String phoneNumber) async {
    _isLoading = true;
    _error = null;
    _validationCode = null;
    _verificationStatus = null;
    notifyListeners();

    MixpanelManager().phoneCallVerificationStarted();

    var result = await api.verifyPhoneNumber(phoneNumber);
    _isLoading = false;

    if (result == null) {
      _error = 'Failed to start verification';
      notifyListeners();
      return false;
    }

    if (result.containsKey('error')) {
      _error = result['error'] as String?;
      notifyListeners();
      return false;
    }

    _validationCode = result['validation_code'] as String?;
    _verificationStatus = result['status'] as String?;
    notifyListeners();
    return true;
  }

  Future<bool> checkVerification(String phoneNumber) async {
    var result = await api.checkPhoneVerification(phoneNumber);
    if (result == null) return false;

    bool verified = result['verified'] == true;
    if (verified) {
      MixpanelManager().phoneCallVerificationCompleted();
      await loadVerifiedNumbers();
    }
    return verified;
  }

  Future<bool> deleteNumber(String phoneNumberId) async {
    var success = await api.deleteVerifiedPhoneNumber(phoneNumberId);
    if (success) {
      _verifiedNumbers.removeWhere((n) => n.id == phoneNumberId);
      notifyListeners();
    }
    return success;
  }

  // ************************************************
  // ************** CALL MANAGEMENT *****************
  // ************************************************

  Future<bool> startCall(String phoneNumber) async {
    if (_callState != PhoneCallState.idle) {
      _error = 'A call is already in progress';
      notifyListeners();
      return false;
    }

    _error = null;
    _lastError = null;
    _callState = PhoneCallState.connecting;
    _remoteNumber = phoneNumber;
    _currentCallId = DateTime.now().millisecondsSinceEpoch.toString();
    _transcriptSegments.clear();
    _isMuted = false;
    _isSpeakerOn = false;
    notifyListeners();

    // Request mic permission first, before any SDK initialization
    var micStatus = await Permission.microphone.request();
    if (!micStatus.isGranted) {
      _callState = PhoneCallState.idle;
      _error = 'Microphone permission is required to make calls';
      notifyListeners();
      return false;
    }

    // Resolve contact name from device contacts
    _contactName = await _resolveContactName(phoneNumber);

    // Get Twilio token
    var token = await api.getPhoneCallToken();
    if (token == null) {
      _callState = PhoneCallState.idle;
      _error = 'Failed to get call token. Verify your phone number first.';
      notifyListeners();
      return false;
    }

    // Initialize native Twilio SDK
    var initialized = await _nativeService.initialize(token.accessToken);
    if (!initialized) {
      _callState = PhoneCallState.idle;
      _error = 'Failed to initialize call service';
      notifyListeners();
      return false;
    }

    // Schedule token refresh before expiry (3-minute buffer)

    _scheduleTokenRefresh(token.ttl);

    // Make the call via native layer
    var callStarted = await _nativeService.makeCall(
      phoneNumber: phoneNumber,
      callId: _currentCallId!,
      contactName: _contactName,
    );

    if (!callStarted) {
      _callState = PhoneCallState.idle;
      _error = 'Failed to start call';
      MixpanelManager().phoneCallFailed(error: 'Failed to start call');
      _disconnectTranscriptionSocket();
      notifyListeners();
      return false;
    }

    MixpanelManager().phoneCallStarted(contactName: _contactName);
    return true;
  }

  Future<void> endCall() async {
    await _nativeService.endCall();
    _onCallEnded();
  }

  void toggleMute() {
    // Don't update state here — wait for native confirmation via _onMuteConfirmed
    _nativeService.toggleMute(!_isMuted);
  }

  void toggleSpeaker() {
    // Don't update state here — wait for native confirmation via _onSpeakerConfirmed
    _nativeService.toggleSpeaker(!_isSpeakerOn);
  }

  Future<void> loadAudioRoutes() async {
    _availableRoutes = await _nativeService.getAudioRoutes();
    notifyListeners();
  }

  Future<void> selectAudioRoute(AudioRoute route) async {
    var success = await _nativeService.selectAudioRoute(route.id);
    if (success) {
      _selectedRoute = route;
      _isSpeakerOn = route.type == AudioRouteType.speaker;
      notifyListeners();
    }
  }

  void sendDtmf(String digit) {
    if (_callState == PhoneCallState.active) {
      _nativeService.sendDtmf(digit);
    }
  }

  // ************************************************
  // ************* SPEAKER LABELS *******************
  // ************************************************

  String getSpeakerLabel(TranscriptSegment segment) {
    if (segment.isUser) return 'You';
    return _contactName ?? _remoteNumber ?? 'Unknown';
  }

  // ************************************************
  // *********** PRIVATE HELPERS ********************
  // ************************************************

  void _onCallStateChanged(PhoneCallState state) {
    _callState = state;
    if (state == PhoneCallState.active && _callStartTime == null) {
      _callStartTime = DateTime.now();
      _startDurationTimer();
      _connectTranscriptionSocket();
      MixpanelManager().phoneCallConnected();
    } else if (state == PhoneCallState.ended || state == PhoneCallState.failed) {
      _onCallEnded();
    }
    notifyListeners();
  }

  void _onAudioData(Uint8List audioData, int channel) {
    var socket = _transcriptionSocket;

    // Buffer audio during WebSocket reconnect
    if (socket == null) {
      if (_audioBuffer.length < _maxAudioBufferSize) {
        var data = Uint8List(1 + audioData.length);
        data[0] = channel;
        data.setRange(1, data.length, audioData);
        _audioBuffer.add(data);
      }
      return;
    }

    try {
      // Flush buffered audio first
      if (_audioBuffer.isNotEmpty) {
        for (var buffered in _audioBuffer) {
          socket.sink.add(buffered);
        }
        _audioBuffer.clear();
      }

      var data = Uint8List(1 + audioData.length);
      data[0] = channel; // 0x01 = user, 0x02 = remote
      data.setRange(1, data.length, audioData);
      socket.sink.add(data);
    } catch (e) {
      Logger.error('PhoneCallProvider: failed to send audio data: $e');
    }
  }

  void _onCallEnded() {
    MixpanelManager().phoneCallEnded(durationSeconds: _callDuration.inSeconds);
    _callState = PhoneCallState.ended;
    _stopDurationTimer();
    _disconnectTranscriptionSocket();
    _tokenRefreshTimer?.cancel();
    _tokenRefreshTimer = null;
    _transcriptionStatus = TranscriptionStatus.idle;
    _audioBuffer.clear();
    notifyListeners();

    // Reset state after a short delay so UI can show "Call Ended"
    Future.delayed(const Duration(seconds: 2), () {
      _callState = PhoneCallState.idle;
      _currentCallId = null;
      _remoteNumber = null;
      _contactName = null;
      _callStartTime = null;
      _callDuration = Duration.zero;
      _transcriptSegments.clear();
      _availableRoutes = [];
      _selectedRoute = null;
      notifyListeners();
    });
  }

  void _onNativeError(PhoneCallError error) {
    _lastError = error;
    _error = error.message;
    Logger.error('PhoneCallProvider: native error: ${error.code} - ${error.message}');
    notifyListeners();
  }

  void _onMuteConfirmed(bool muted) {
    _isMuted = muted;
    notifyListeners();
  }

  void _onSpeakerConfirmed(bool speakerOn) {
    _isSpeakerOn = speakerOn;
    notifyListeners();
  }

  void _scheduleTokenRefresh(int ttlSeconds) {
    _tokenRefreshTimer?.cancel();
    // Refresh 3 minutes before expiry (or half TTL if TTL < 6 min)
    var refreshInSeconds = ttlSeconds > 360 ? ttlSeconds - 180 : ttlSeconds ~/ 2;
    if (refreshInSeconds <= 0) return;

    Logger.info('PhoneCallProvider: scheduling token refresh in ${refreshInSeconds}s');
    _tokenRefreshTimer = Timer(Duration(seconds: refreshInSeconds), () async {
      if (_callState != PhoneCallState.active && _callState != PhoneCallState.ringing) return;
      Logger.info('PhoneCallProvider: refreshing call token');
      var token = await api.getPhoneCallToken();
      if (token != null) {
        await _nativeService.initialize(token.accessToken);
        _scheduleTokenRefresh(token.ttl);
      } else {
        Logger.error('PhoneCallProvider: token refresh failed, retrying in 30s');
        _scheduleTokenRefresh(60);
      }
    });
  }

  void _startDurationTimer() {
    _durationTimer?.cancel();
    _durationTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_callStartTime != null) {
        _callDuration = DateTime.now().difference(_callStartTime!);
        notifyListeners();
      }
    });
  }

  void _stopDurationTimer() {
    _durationTimer?.cancel();
    _durationTimer = null;
  }

  // ************************************************
  // *********** TRANSCRIPTION SOCKET ***************
  // ************************************************

  Future<void> _connectTranscriptionSocket() async {
    if (_currentCallId == null) return;

    _wsReconnectTimer?.cancel();
    _wsReconnectTimer = null;
    _transcriptionStatus = TranscriptionStatus.connecting;
    notifyListeners();

    var language =
        SharedPreferencesUtil().hasSetPrimaryLanguage ? SharedPreferencesUtil().userPrimaryLanguage : 'multi';

    var wsUrl = api.buildPhoneCallWebSocketUrl(
      callId: _currentCallId!,
      uid: SharedPreferencesUtil().uid,
      language: language,
    );
    Logger.info('PhoneCallProvider: connecting to $wsUrl');

    try {
      var headers = await buildHeaders(requireAuthCheck: true);
      _transcriptionSocket = IOWebSocketChannel.connect(
        wsUrl,
        headers: headers,
        pingInterval: const Duration(seconds: 20),
      );
      _transcriptionSocket!.stream.listen(
        (message) {
          if (_transcriptionStatus != TranscriptionStatus.active) {
            _transcriptionStatus = TranscriptionStatus.active;
            notifyListeners();
          }
          if (message is String) {
            _handleTranscriptionMessage(message);
          }
        },
        onError: (error) {
          Logger.error('PhoneCallProvider: WebSocket error: $error');
          _transcriptionSocket = null;
          _scheduleReconnect();
        },
        onDone: () {
          Logger.info('PhoneCallProvider: WebSocket closed');
          _transcriptionSocket = null;
          _scheduleReconnect();
        },
      );
      _wsReconnectAttempts = 0;
    } catch (e) {
      Logger.error('PhoneCallProvider: failed to connect WebSocket: $e');
      _transcriptionSocket = null;
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_callState != PhoneCallState.active) return;
    if (_wsReconnectAttempts >= _maxWsReconnectAttempts) {
      Logger.error('PhoneCallProvider: max reconnect attempts reached, giving up');
      _transcriptionStatus = TranscriptionStatus.failed;
      notifyListeners();
      return;
    }

    _transcriptionStatus = TranscriptionStatus.reconnecting;
    notifyListeners();

    var delay = Duration(seconds: 1 << _wsReconnectAttempts); // 1s, 2s, 4s, 8s...
    _wsReconnectAttempts++;
    Logger.info('PhoneCallProvider: reconnecting WebSocket in ${delay.inSeconds}s (attempt $_wsReconnectAttempts)');

    _wsReconnectTimer = Timer(delay, () {
      if (_callState == PhoneCallState.active) {
        _connectTranscriptionSocket();
      }
    });
  }

  void _disconnectTranscriptionSocket() {
    _wsReconnectTimer?.cancel();
    _wsReconnectTimer = null;
    _wsReconnectAttempts = 0;
    _transcriptionSocket?.sink.close();
    _transcriptionSocket = null;
  }

  void _handleTranscriptionMessage(String message) {
    if (message == 'ping') return;

    try {
      var data = jsonDecode(message);

      // Standard segment array format: [{id, text, is_user, speaker, start, end, ...}, ...]
      if (data is List) {
        for (var segmentJson in data) {
          var segment = TranscriptSegment.fromJson(segmentJson as Map<String, dynamic>);
          var existingIndex = _transcriptSegments.indexWhere((s) => s.id == segment.id);
          if (existingIndex >= 0) {
            _transcriptSegments[existingIndex] = segment;
          } else {
            _transcriptSegments.add(segment);
          }
        }
        if (data.isNotEmpty) notifyListeners();
        return;
      }

      // Handle translation events
      if (data is Map && data['type'] == 'translating') {
        var segments = data['segments'] as List<dynamic>? ?? [];
        for (var segmentJson in segments) {
          var translated = TranscriptSegment.fromJson(segmentJson as Map<String, dynamic>);
          var existingIndex = _transcriptSegments.indexWhere((s) => s.id == translated.id);
          if (existingIndex >= 0) {
            _transcriptSegments[existingIndex].translations = translated.translations;
          }
        }
        if (segments.isNotEmpty) notifyListeners();
        return;
      }
    } catch (e) {
      Logger.error('PhoneCallProvider: failed to parse transcript message: $e');
    }
  }

  // ************************************************
  // *********** CONTACT RESOLUTION *****************
  // ************************************************

  Future<String?> _resolveContactName(String phoneNumber) async {
    try {
      bool hasPermission = await FlutterContacts.requestPermission(readonly: true);
      if (!hasPermission) return null;

      var contacts = await FlutterContacts.getContacts(withProperties: true, withPhoto: false);
      var cleaned = _cleanPhoneNumber(phoneNumber);

      for (var contact in contacts) {
        for (var phone in contact.phones) {
          if (_cleanPhoneNumber(phone.number) == cleaned) {
            return contact.displayName;
          }
        }
      }
    } catch (e) {
      Logger.error('PhoneCallProvider: contact resolution failed: $e');
    }
    return null;
  }

  String _cleanPhoneNumber(String number) {
    return number.replaceAll(RegExp(r'[\s\-\(\)]'), '');
  }

  @override
  void dispose() {
    _stopDurationTimer();
    _disconnectTranscriptionSocket();
    _tokenRefreshTimer?.cancel();
    _nativeService.dispose();
    super.dispose();
  }
}
