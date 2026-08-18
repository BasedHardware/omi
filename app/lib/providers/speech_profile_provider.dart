import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/utils/logger.dart';

/// Enum for loading text states in speech profile
enum SpeechProfileLoadingState { uploading, memorizing, personalizing, allSet }

/// Enum for progress message states in speech profile
enum SpeechProfileProgressState { keepSpeaking, keepGoing, almostThere, soClose }

class SpeechProfileProvider extends ChangeNotifier
    with MessageNotifierMixin
    implements IDeviceServiceSubsciption, ITransctiptSegmentSocketServiceListener {
  DeviceProvider? deviceProvider;
  bool? permissionEnabled;
  bool loading = false;
  BtDevice? device;

  final targetWordsCount = 70;
  final maxDuration = 150;

  StreamSubscription? connectionStateListener;
  List<TranscriptSegment> segments = [];
  double? streamStartedAtSecond;
  late WavBytesUtil audioStorage;
  StreamSubscription? _bleBytesStream;

  TranscriptSegmentSocketService? _socket;

  bool startedRecording = false;
  double percentageCompleted = 0;
  bool uploadingProfile = false;
  bool profileCompleted = false;
  Timer? forceCompletionTimer;
  Timer? _reconnectTimer;
  bool _reconnecting = false;

  bool isInitialising = false;
  bool isInitialised = false;

  String text = '';
  SpeechProfileProgressState progressState = SpeechProfileProgressState.keepSpeaking;

  Function? _finalizedCallback;
  Function? _processConversationCallback;

  /// only used during onboarding /////
  SpeechProfileLoadingState loadingState = SpeechProfileLoadingState.uploading;
  ServerConversation? conversation;

  // Onboarding state (questions from server)
  bool usePhoneMic = false;
  String currentQuestion = '';
  int currentQuestionIndex = 0;
  int totalQuestions = 0;

  double get questionProgress => totalQuestions == 0 ? 0.0 : (currentQuestionIndex / totalQuestions).clamp(0.0, 1.0);

  void skipCurrentQuestion() {
    if (_socket?.state == SocketServiceState.connected) {
      _socket?.sendText('{"type": "skip_question"}');
    }
  }

  void updateLoadingState(SpeechProfileLoadingState state) {
    loadingState = state;
    notifyListeners();
  }

  void setInitialising(bool value) {
    isInitialising = value;
    notifyListeners();
  }

  void setInitialised(bool value) {
    isInitialised = value;
    notifyListeners();
  }

  void setProviders(DeviceProvider provider) {
    deviceProvider = provider;
    notifyListeners();
  }

  Future<void> updateDevice() async {
    if (device == null) {
      await deviceProvider?.scanAndConnectToDevice();
      device = deviceProvider?.connectedDevice;
    }
    notifyListeners();
  }

  Future<bool> initialise({
    Function? finalizedCallback,
    Function? processConversationCallback,
    bool usePhoneMic = false,
  }) async {
    _finalizedCallback = finalizedCallback;
    _processConversationCallback = processConversationCallback;
    setInitialising(true);
    this.usePhoneMic = usePhoneMic;

    try {
      if (usePhoneMic) {
        // Phone microphone mode - use PCM16 at 16kHz
        const codec = BleAudioCodec.pcm16;
        audioStorage = WavBytesUtil(codec: codec, framesPerSecond: 100);
        await _initiateWebsocket(codec: codec, sampleRate: 16000, force: true);

        // Start phone mic streaming
        if (!await _initiatePhoneMicStreaming()) {
          notifyError('SOCKET_INIT_FAILED');
          return false;
        }
      } else {
        // Device mode - use device codec
        device = deviceProvider?.connectedDevice;
        BleAudioCodec codec = await _getAudioCodec(device!.id);
        audioStorage = WavBytesUtil(codec: codec, framesPerSecond: codec.getFramesPerSecond());
        await _initiateWebsocket(codec: codec, force: true);

        if (device != null) await initiateFriendAudioStreaming();
      }

      if (_socket?.state != SocketServiceState.connected) {
        // wait for websocket to connect
        await Future.delayed(const Duration(seconds: 2));
      }

      setInitialised(true);
      return true;
    } catch (e) {
      Logger.debug('Error during initialise: $e');
      notifyError('SOCKET_INIT_FAILED');
      return false;
    } finally {
      setInitialising(false);
      notifyListeners();
    }
  }

  void updateStartedRecording(bool value) {
    startedRecording = value;
    notifyListeners();
  }

  changeLoadingState(bool value) {
    loading = value;
    notifyListeners();
  }

  initiateConnectionListener() async {
    if (device == null || connectionStateListener != null) return;
    ServiceManager.instance().device.subscribe(this, this);
  }

  Future<void> _initiateWebsocket({required BleAudioCodec codec, int? sampleRate, bool force = false}) async {
    String language =
        SharedPreferencesUtil().hasSetPrimaryLanguage ? SharedPreferencesUtil().userPrimaryLanguage : "multi";
    int rate = sampleRate ?? (codec.isOpusSupported() ? 16000 : 8000);

    _socket = await openSpeechProfileSocket(
      codec: codec,
      sampleRate: rate,
      language: language,
      force: force,
    );
    if (_socket == null) {
      throw Exception("Can not create new speech profile socket");
    }
    _socket?.subscribe(this, this);
    await _socket?.requestFirstOnboardingQuestion();
  }

  /// Opens the speech-profile socket. Overridden in tests to control the
  /// timing of an attempt; production always goes through the socket service
  /// pool. Mirrors CaptureProvider.openConversationSocket.
  @visibleForTesting
  Future<TranscriptSegmentSocketService?> openSpeechProfileSocket({
    required BleAudioCodec codec,
    required int sampleRate,
    required String language,
    required bool force,
  }) {
    return ServiceManager.instance().socket.speechProfile(
          codec: codec,
          sampleRate: sampleRate,
          language: language,
          force: force,
        );
  }

  /// Uploads the recorded speech-profile audio. Overridden in tests to avoid
  /// a real network call.
  @visibleForTesting
  Future<bool> uploadSpeechProfile(File file) => uploadProfile(file);

  /// Start phone microphone streaming (alternative to BLE device streaming).
  /// Returns false when the mic could not be acquired — contention with a live
  /// conversation throws a [StateError] — so [initialise] fails visibly instead
  /// of leaving a recording UI that never receives audio.
  Future<bool> _initiatePhoneMicStreaming() async {
    Logger.debug('Starting phone mic streaming for speech profile...');

    // Request mic permission
    await Permission.microphone.request();

    try {
      await ServiceManager.instance().mic.start(
        onByteReceived: (Uint8List bytes) {
          if (bytes.isEmpty) return;

          // Store audio frames for speech profile upload
          audioStorage.frames.add(bytes.toList());

          // Send to transcription socket
          if (_socket?.state == SocketServiceState.connected) {
            _socket?.send(bytes);
          }
        },
        onRecording: () {
          Logger.debug('Phone mic recording started');
          updateStartedRecording(true);
        },
        onStop: () {
          Logger.debug('Phone mic recording stopped');
        },
      );
      return true;
    } catch (e) {
      Logger.debug('Speech profile: phone mic start failed: $e');
      return false;
    }
  }

  /// Stop phone microphone streaming
  void _stopPhoneMicStreaming() {
    if (usePhoneMic) {
      Logger.debug('Stopping phone mic streaming');
      ServiceManager.instance().mic.stop();
    }
  }

  Future finalize() async {
    try {
      if (uploadingProfile || profileCompleted) return;

      uploadingProfile = true;
      notifyListeners();

      _stopPhoneMicStreaming();

      await _socket?.stop(reason: 'finalizing');
      forceCompletionTimer?.cancel();
      connectionStateListener?.cancel();
      _bleBytesStream?.cancel();

      updateLoadingState(SpeechProfileLoadingState.memorizing);
      Logger.debug('Creating WAV file...');
      var data = await audioStorage.createWavFile(filename: 'speaker_profile.wav');
      Logger.debug('WAV file created, uploading profile...');

      bool uploadSuccess = false;
      bool uploadFailedDueToShortAudio = false;
      try {
        uploadSuccess = await uploadSpeechProfile(data.item1).timeout(
          const Duration(seconds: 30),
          onTimeout: () {
            Logger.debug('Profile upload timed out after 30 seconds');
            return false;
          },
        );
        Logger.debug('Profile upload completed: $uploadSuccess');
      } catch (e) {
        Logger.debug('Error uploading profile: $e');
        final error = e.toString().toLowerCase();
        uploadFailedDueToShortAudio = error.contains('audio duration is invalid') || error.contains('audio is empty');
        uploadSuccess = false;
      }

      if (!uploadSuccess) {
        completeAfterUploadFailure(tooShort: uploadFailedDueToShortAudio);
        return;
      }

      SharedPreferencesUtil().hasSpeakerProfile = true;
      Logger.debug('Speaker profile saved to preferences');

      updateLoadingState(SpeechProfileLoadingState.personalizing);

      // Trigger conversation processing before marking complete
      if (_processConversationCallback != null) {
        Logger.debug('Triggering conversation processing...');
        _processConversationCallback!();
      }

      _reconnectTimer?.cancel();
      _reconnectTimer = null;
      uploadingProfile = false;
      profileCompleted = true;
      text = '';
      updateLoadingState(SpeechProfileLoadingState.allSet);
      notifyListeners();
    } finally {
      if (_finalizedCallback != null) {
        _finalizedCallback!();
      }
    }
  }

  /// Upload failed - notify user but still complete onboarding. A failed
  /// voice-print upload (e.g. no speech-profiles bucket configured, as in the
  /// local dev harness) is a degraded feature, not a reason to trap the user
  /// on the last onboarding question forever: the "All Done" continue button
  /// in speech_profile_widget.dart is gated on profileCompleted, which this
  /// branch previously never set. Separated from finalize() so it's directly
  /// testable without a real (opus-decoder-backed) WavBytesUtil.
  @visibleForTesting
  void completeAfterUploadFailure({required bool tooShort}) {
    uploadingProfile = false;
    notifyError(tooShort ? 'TOO_SHORT' : 'UPLOAD_FAILED');

    // Still trigger conversation processing
    if (_processConversationCallback != null) {
      Logger.debug('Triggering conversation processing despite upload failure...');
      _processConversationCallback!();
    }

    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    profileCompleted = true;
    text = '';
    updateLoadingState(SpeechProfileLoadingState.allSet);
    notifyListeners();
  }

  // TODO: use connection directly
  Future<BleAudioCodec> _getAudioCodec(String deviceId) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return BleAudioCodec.pcm8;
    }
    return connection.getAudioCodec();
  }

  Future<StreamSubscription?> _getBleAudioBytesListener(
    String deviceId, {
    required void Function(List<int>) onAudioBytesReceived,
  }) async {
    var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
    if (connection == null) {
      return Future.value(null);
    }
    return connection.getBleAudioBytesListener(onAudioBytesReceived: onAudioBytesReceived);
  }

  Future<void> initiateFriendAudioStreaming() async {
    _bleBytesStream = await _getBleAudioBytesListener(
      device!.id,
      onAudioBytesReceived: (List<int> value) {
        if (value.isEmpty) return;

        // Only remove 3-byte header for Omi/OpenGlass devices
        final paddingLeft = (device?.type == DeviceType.omi || device?.type == DeviceType.openglass) ? 3 : 0;

        // Store frame: use storeFramePacket for Omi/OpenGlass (expects header),
        // or append frames directly for other devices (raw frames)
        if (paddingLeft > 0) {
          audioStorage.storeFramePacket(value);
        } else {
          audioStorage.frames.add(value);
        }

        final trimmedValue = paddingLeft > 0 ? value.sublist(paddingLeft) : value;
        if (_socket?.state == SocketServiceState.connected) {
          _socket?.send(trimmedValue);
        }
      },
    );
  }

  _validateSingleSpeaker() {
    // Filter out Omi question segments for speaker validation
    final userSegments = segments.where((e) => e.speakerId != omiSpeakerId).toList();

    int speakersCount = userSegments.map((e) => e.speaker).toSet().length;
    Logger.debug('_validateSingleSpeaker speakers count: $speakersCount');
    if (speakersCount > 1) {
      var speakerToWords = userSegments.fold<Map<int, int>>({}, (previousValue, element) {
        previousValue[element.speakerId] = (previousValue[element.speakerId] ?? 0) + element.text.split(' ').length;
        return previousValue;
      });
      Logger.debug('speakerToWords: $speakerToWords');
      if (speakerToWords.values.every((element) => element / userSegments.length > 0.08)) {
        notifyError('MULTIPLE_SPEAKERS');
      }
    }
  }

  void resetSegments() {
    segments.clear();
    streamStartedAtSecond = null;
    audioStorage.clearAudioBytes();
    text = '';
    percentageCompleted = 0;
    notifyListeners();
  }

  Future setupSpeechRecording() async {
    final permission = await getStoreRecordingPermission();
    permissionEnabled = permission;
    if (permission != null) {
      SharedPreferencesUtil().permissionStoreRecordingsEnabled = permission;
    }
    notifyListeners();
  }

  void updateProgressMessage() {
    // Only show user's speech, not Omi questions
    text = segments.where((e) => e.speakerId != omiSpeakerId).map((e) => e.text).join(' ').trim();
    int wordsCount = text.split(' ').length;
    progressState = SpeechProfileProgressState.keepSpeaking;
    if (wordsCount > 10) {
      progressState = SpeechProfileProgressState.keepGoing;
    } else if (wordsCount > 25) {
      progressState = SpeechProfileProgressState.almostThere;
    } else if (wordsCount > 40) {
      progressState = SpeechProfileProgressState.soClose;
    }
    notifyListeners();
  }

  Future close() async {
    connectionStateListener?.cancel();
    _bleBytesStream?.cancel();
    forceCompletionTimer?.cancel();
    _reconnectTimer?.cancel();
    _reconnectTimer = null;

    _stopPhoneMicStreaming();

    segments.clear();
    text = '';
    currentQuestion = '';
    currentQuestionIndex = 0;
    totalQuestions = 0;
    startedRecording = false;
    percentageCompleted = 0;
    uploadingProfile = false;
    profileCompleted = false;
    usePhoneMic = false;
    _processConversationCallback = null;

    await _socket?.stop(reason: 'closing');
    notifyListeners();
  }

  @override
  void dispose() {
    connectionStateListener?.cancel();
    _bleBytesStream?.cancel();
    forceCompletionTimer?.cancel();
    _reconnectTimer?.cancel();
    _finalizedCallback = null;
    _socket?.unsubscribe(this);
    ServiceManager.instance().device.unsubscribe(this);

    super.dispose();
  }

  @override
  void onDeviceConnectionStateChanged(String deviceId, DeviceConnectionState state) async {
    switch (state) {
      case DeviceConnectionState.connected:
        var connection = await ServiceManager.instance().device.ensureConnection(deviceId);
        if (connection == null) {
          return;
        }
        device = connection.device;
        notifyListeners();
        initiateFriendAudioStreaming();
        break;
      case DeviceConnectionState.disconnected:
        if (deviceId == device?.id) {
          device = null;
          notifyListeners();
        }
      default:
        Logger.debug("Device connection state is not supported $state");
    }
  }

  @override
  void onDevices(List<BtDevice> devices) {}

  @override
  void onStatusChanged(DeviceServiceStatus status) {}

  @override
  void onClosed([int? closeCode]) {
    Logger.debug('Speech profile socket closed with code: $closeCode');
    // Only notify error if we're still recording and not completed
    if (startedRecording && !profileCompleted && !uploadingProfile) {
      notifyError('SOCKET_DISCONNECTED');
      _scheduleReconnect();
    }
  }

  @override
  void onError(Object err) {
    Logger.debug('Speech profile socket error: $err');
    if (startedRecording && !profileCompleted && !uploadingProfile) {
      notifyError('SOCKET_ERROR');
      _scheduleReconnect();
    }
  }

  /// Retry connecting on an interval until it succeeds or the flow ends.
  ///
  /// Unlike the main capture socket (CaptureProvider._startKeepAliveServices),
  /// this socket previously had no reconnect at all: once dropped,
  /// skipCurrentQuestion() and outgoing mic audio are both no-ops gated on
  /// `_socket?.state == connected` (see below), so onboarding hung forever
  /// until the app was force-relaunched.
  ///
  /// The backend keeps no onboarding state across connections
  /// (OnboardingHandler is constructed fresh per websocket in
  /// routers/listen/runtime.py), so a reconnect always restarts the question
  /// sequence from the top. Reset locally to match rather than showing a
  /// stale question index against a server that has actually restarted.
  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer.periodic(const Duration(seconds: 5), (timer) async {
      if (profileCompleted || uploadingProfile || _socket?.state == SocketServiceState.connected) {
        timer.cancel();
        return;
      }

      // _initiateWebsocket is async, so without this guard a slow attempt
      // still in flight would overlap with the next 5s tick and open a
      // second socket concurrently — the same failure mode CaptureProvider's
      // keep-alive hit in #11305.
      if (_reconnecting) return;
      _reconnecting = true;

      Logger.debug('Speech profile socket reconnect attempt');
      try {
        if (usePhoneMic) {
          await _initiateWebsocket(codec: BleAudioCodec.pcm16, sampleRate: 16000, force: true);
        } else if (device != null) {
          final codec = await _getAudioCodec(device!.id);
          await _initiateWebsocket(codec: codec, force: true);
        } else {
          return;
        }

        currentQuestionIndex = 0;
        currentQuestion = '';
        notifyListeners();
      } catch (e) {
        Logger.debug('Speech profile socket reconnect failed: $e');
      } finally {
        _reconnecting = false;
      }
    });
  }

  @override
  void onMessageEventReceived(MessageEvent event) {
    Logger.debug('onMessageEventReceived: ${event.eventType}');

    if (event is OnboardingQuestionEvent) {
      currentQuestion = event.question;
      currentQuestionIndex = event.questionIndex;
      totalQuestions = event.totalQuestions;
      Logger.debug('Received question ${event.questionIndex + 1}/${event.totalQuestions}: ${event.question}');
      notifyListeners();
    } else if (event is OnboardingQuestionAnsweredEvent) {
      Logger.debug('Question ${event.questionIndex} answered');
      notifyInfo('NEXT_QUESTION');
    } else if (event is OnboardingCompleteEvent) {
      Logger.debug('Onboarding complete from backend: conversationId=${event.conversationId}');
      finalize();
    }
  }

  @override
  void onSegmentReceived(List<TranscriptSegment> newSegments) {
    if (newSegments.isEmpty) return;

    Logger.debug('onSegmentReceived: ${newSegments.length} new segments, existing: ${segments.length}');

    // Filter out Omi question segments for audio trimming calculation
    final userSegments = newSegments.where((s) => s.speakerId != omiSpeakerId).toList();

    if (segments.isEmpty && userSegments.isNotEmpty) {
      audioStorage.removeFramesRange(fromSecond: 0, toSecond: userSegments[0].start.toInt());
    }
    if (userSegments.isNotEmpty) {
      streamStartedAtSecond ??= userSegments[0].start;
    }

    final remainSegments = TranscriptSegment.updateSegments(segments, newSegments);
    segments.addAll(remainSegments);

    // Validate single speaker (exclude Omi segments)
    _validateSingleSpeaker();

    // Display only user's speech, not Omi's questions
    text = segments.where((e) => e.speakerId != omiSpeakerId).map((e) => e.text).join(' ').trim();
    percentageCompleted = questionProgress;

    notifyInfo('SCROLL_DOWN');
    notifyListeners();
  }

  @override
  void onConnected() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
  }
}
