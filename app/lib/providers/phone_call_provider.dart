import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'package:omi/backend/http/api/phone_calls.dart' as api;
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/services/phone_call_service.dart';
import 'package:omi/utils/logger.dart';

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
  final List<PhoneTranscriptSegment> _transcriptSegments = [];
  List<PhoneTranscriptSegment> get transcriptSegments => List.unmodifiable(_transcriptSegments);

  // WebSocket for transcription
  WebSocketChannel? _transcriptionSocket;

  // Verified phone numbers
  List<VerifiedPhoneNumber> _verifiedNumbers = [];
  List<VerifiedPhoneNumber> get verifiedNumbers => _verifiedNumbers;

  // Loading states
  bool _isLoading = false;
  bool get isLoading => _isLoading;

  String? _error;
  String? get error => _error;

  Future<void>? _initialLoad;
  Future<void> get initialLoad => _initialLoad ?? Future.value();

  PhoneCallProvider() {
    _nativeService.onCallStateChanged = _onCallStateChanged;
    _nativeService.onAudioData = _onAudioData;
    _nativeService.startListening();
    _initialLoad = loadVerifiedNumbers();
  }

  // ************************************************
  // *********** PHONE NUMBER MANAGEMENT ************
  // ************************************************

  Future<void> loadVerifiedNumbers() async {
    _verifiedNumbers = await api.getVerifiedPhoneNumbers();
    notifyListeners();
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

    var result = await api.verifyPhoneNumber(phoneNumber);
    _isLoading = false;

    if (result == null) {
      _error = 'Failed to start verification';
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
    _callState = PhoneCallState.connecting;
    _remoteNumber = phoneNumber;
    _currentCallId = DateTime.now().millisecondsSinceEpoch.toString();
    _transcriptSegments.clear();
    _isMuted = false;
    _isSpeakerOn = false;
    notifyListeners();

    // Resolve contact name from device contacts
    _contactName = await _resolveContactName(phoneNumber);

    // Get Twilio token
    var token = await api.getPhoneCallToken();
    if (token == null) {
      _callState = PhoneCallState.failed;
      _error = 'Failed to get call token. Verify your phone number first.';
      notifyListeners();
      return false;
    }

    // Initialize native Twilio SDK
    var initialized = await _nativeService.initialize(token.accessToken);
    if (!initialized) {
      _callState = PhoneCallState.failed;
      _error = 'Failed to initialize call service';
      notifyListeners();
      return false;
    }

    // Connect transcription WebSocket
    await _connectTranscriptionSocket();

    // Make the call via native layer
    var callStarted = await _nativeService.makeCall(
      phoneNumber: phoneNumber,
      callId: _currentCallId!,
      contactName: _contactName,
    );

    if (!callStarted) {
      _callState = PhoneCallState.failed;
      _error = 'Failed to start call';
      _disconnectTranscriptionSocket();
      notifyListeners();
      return false;
    }

    return true;
  }

  Future<void> endCall() async {
    await _nativeService.endCall();
    _onCallEnded();
  }

  void toggleMute() {
    _isMuted = !_isMuted;
    _nativeService.toggleMute(_isMuted);
    notifyListeners();
  }

  void toggleSpeaker() {
    _isSpeakerOn = !_isSpeakerOn;
    _nativeService.toggleSpeaker(_isSpeakerOn);
    notifyListeners();
  }

  // ************************************************
  // ************* SPEAKER LABELS *******************
  // ************************************************

  String getSpeakerLabel(PhoneTranscriptSegment segment) {
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
    } else if (state == PhoneCallState.ended || state == PhoneCallState.failed) {
      _onCallEnded();
    }
    notifyListeners();
  }

  void _onAudioData(Uint8List audioData, int channel) {
    // Forward audio data to WebSocket with channel prefix
    if (_transcriptionSocket != null) {
      var data = Uint8List(1 + audioData.length);
      data[0] = channel; // 0x01 = user, 0x02 = remote
      data.setRange(1, data.length, audioData);
      _transcriptionSocket!.sink.add(data);
    }
  }

  void _onCallEnded() {
    _callState = PhoneCallState.ended;
    _stopDurationTimer();
    _disconnectTranscriptionSocket();
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
      notifyListeners();
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
          if (message is String) {
            _handleTranscriptionMessage(message);
          }
        },
        onError: (error) {
          Logger.error('PhoneCallProvider: WebSocket error: $error');
        },
        onDone: () {
          Logger.info('PhoneCallProvider: WebSocket closed');
        },
      );
    } catch (e) {
      Logger.error('PhoneCallProvider: failed to connect WebSocket: $e');
    }
  }

  void _disconnectTranscriptionSocket() {
    _transcriptionSocket?.sink.close();
    _transcriptionSocket = null;
  }

  void _handleTranscriptionMessage(String message) {
    try {
      var data = jsonDecode(message);
      var type = data['type'] as String?;

      if (type == 'phone_transcript') {
        var segmentJson = data['segment'] as Map<String, dynamic>;
        var segment = PhoneTranscriptSegment.fromJson(segmentJson);

        // Update existing segment in place, or append new ones at the end
        var existingIndex = _transcriptSegments.indexWhere((s) => s.id == segment.id);
        if (existingIndex >= 0) {
          _transcriptSegments[existingIndex] = segment;
        } else {
          _transcriptSegments.add(segment);
        }
        notifyListeners();
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
    _nativeService.dispose();
    super.dispose();
  }
}
