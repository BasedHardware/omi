import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
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
import 'package:permission_handler/permission_handler.dart';

class SpeechProfileProvider extends ChangeNotifier
    with MessageNotifierMixin
    implements IDeviceServiceSubsciption, ITransctiptSegmentSocketServiceListener {
  DeviceProvider? deviceProvider;
  bool? permissionEnabled;
  bool loading = false;
  BtDevice? device;

  final targetWordsCount = 70;
  final maxDuration = 150;

  StreamSubscription<OnConnectionStateChangedEvent>? connectionStateListener;
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

  bool isInitialising = false;
  bool isInitialised = false;

  String text = '';
  String message = '';

  late Function? _finalizedCallback;

  /// only used during onboarding /////
  String loadingText = 'Uploading your voice profile....';
  ServerConversation? conversation;
  
  // Onboarding state (questions from server)
  bool usePhoneMic = false;
  String currentQuestion = '';
  int currentQuestionIndex = 0;
  int totalQuestions = 0;

  double get questionProgress => totalQuestions == 0
      ? 0.0
      : (currentQuestionIndex / totalQuestions).clamp(0.0, 1.0);

  void skipCurrentQuestion() {
    if (_socket?.state == SocketServiceState.connected) {
      _socket?.sendText('{"type": "skip_question"}');
    }
  }

  void updateLoadingText(String text) {
    loadingText = text;
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

  Future<void> initialise({Function? finalizedCallback, bool usePhoneMic = false}) async {
    _finalizedCallback = finalizedCallback;
    setInitialising(true);
    this.usePhoneMic = usePhoneMic;
    
    if (usePhoneMic) {
      // Phone microphone mode - use PCM16 at 16kHz
      const codec = BleAudioCodec.pcm16;
      audioStorage = WavBytesUtil(codec: codec, framesPerSecond: 100);
      await _initiateWebsocket(codec: codec, sampleRate: 16000, force: true);
      
      // Start phone mic streaming
      await _initiatePhoneMicStreaming();
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

    setInitialising(false);
    setInitialised(true);
    notifyListeners();
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

    _socket = await ServiceManager.instance()
        .socket
        .speechProfile(codec: codec, sampleRate: rate, language: language, force: force);
    if (_socket == null) {
      throw Exception("Can not create new speech profile socket");
    }
    _socket?.subscribe(this, this);
  }
  
  /// Start phone microphone streaming (alternative to BLE device streaming)
  Future<void> _initiatePhoneMicStreaming() async {
    debugPrint('Starting phone mic streaming for speech profile...');
    
    // Request mic permission
    await Permission.microphone.request();
    
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
        debugPrint('Phone mic recording started');
        updateStartedRecording(true);
      },
      onStop: () {
        debugPrint('Phone mic recording stopped');
      },
    );
  }
  
  /// Stop phone microphone streaming
  void _stopPhoneMicStreaming() {
    if (usePhoneMic) {
      debugPrint('Stopping phone mic streaming');
      ServiceManager.instance().mic.stop();
    }
  }

  _handleCompletion() async {
    if (uploadingProfile || profileCompleted) return;
    String text = segments.map((e) => e.text).join(' ').trim();
    int wordsCount = text.split(' ').length;
    percentageCompleted = (wordsCount / targetWordsCount).clamp(0, 1);
    notifyListeners();
    if (percentageCompleted == 1) {
      await finalize();
    }
    notifyListeners();
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

      updateLoadingText('Memorizing your voice...');
      debugPrint('Creating WAV file...');
      var data = await audioStorage.createWavFile(filename: 'speaker_profile.wav');
      debugPrint('WAV file created, uploading profile...');
      try {
        await uploadProfile(data.item1).timeout(
          const Duration(seconds: 30),
          onTimeout: () {
            debugPrint('Profile upload timed out after 30 seconds');
            return false;
          },
        );
        debugPrint('Profile upload completed');
      } catch (e) {
        debugPrint('Error uploading profile: $e');
      }

      SharedPreferencesUtil().hasSpeakerProfile = true;
      debugPrint('Speaker profile saved to preferences');

      updateLoadingText('Personalizing your experience...');
      uploadingProfile = false;
      profileCompleted = true;
      text = '';
      updateLoadingText("You're all set!");
      notifyListeners();
    } finally {
      if (_finalizedCallback != null) {
        _finalizedCallback!();
      }
    }
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
    int speakersCount = segments.map((e) => e.speaker).toSet().length;
    debugPrint('_validateSingleSpeaker speakers count: $speakersCount');
    if (speakersCount > 1) {
      var speakerToWords = segments.fold<Map<int, int>>(
        {},
        (previousValue, element) {
          previousValue[element.speakerId] = (previousValue[element.speakerId] ?? 0) + element.text.split(' ').length;
          return previousValue;
        },
      );
      debugPrint('speakerToWords: $speakerToWords');
      if (speakerToWords.values.every((element) => element / segments.length > 0.08)) {
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
    text = segments.map((e) => e.text).join(' ').trim();
    int wordsCount = text.split(' ').length;
    message = 'Keep speaking until you get 100%.';
    if (wordsCount > 10) {
      message = 'Keep going, you are doing great';
    } else if (wordsCount > 25) {
      message = 'Great job, you are almost there';
    } else if (wordsCount > 40) {
      message = 'So close, just a little more';
    }
    notifyListeners();
  }

  Future close() async {
    connectionStateListener?.cancel();
    _bleBytesStream?.cancel();
    forceCompletionTimer?.cancel();

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

    await _socket?.stop(reason: 'closing');
    notifyListeners();
  }

  @override
  void dispose() {
    connectionStateListener?.cancel();
    _bleBytesStream?.cancel();
    forceCompletionTimer?.cancel();
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
        debugPrint("Device connection state is not supported $state");
    }
  }

  @override
  void onDevices(List<BtDevice> devices) {}

  @override
  void onStatusChanged(DeviceServiceStatus status) {}

  @override
  void onClosed([int? closeCode]) {
    debugPrint('Speech profile socket closed with code: $closeCode');
    // Only notify error if we're still recording and not completed
    if (startedRecording && !profileCompleted && !uploadingProfile) {
      notifyError('SOCKET_DISCONNECTED');
    }
  }

  @override
  void onError(Object err) {
    debugPrint('Speech profile socket error: $err');
    if (startedRecording && !profileCompleted && !uploadingProfile) {
      notifyError('SOCKET_ERROR');
    }
  }

  @override
  void onMessageEventReceived(MessageEvent event) {
    debugPrint('onMessageEventReceived: ${event.eventType}');

    if (event is OnboardingQuestionEvent) {
      currentQuestion = event.question;
      currentQuestionIndex = event.questionIndex;
      totalQuestions = event.totalQuestions;
      text = '';
      debugPrint('Received question ${event.questionIndex + 1}/${event.totalQuestions}: ${event.question}');
      notifyListeners();
    } else if (event is OnboardingQuestionAnsweredEvent) {
      debugPrint('Question ${event.questionIndex} answered');
      notifyInfo('NEXT_QUESTION');
    } else if (event is OnboardingCompleteEvent) {
      debugPrint('Onboarding complete from backend: conversationId=${event.conversationId}');
      finalize();
    }
  }

  @override
  void onSegmentReceived(List<TranscriptSegment> newSegments) {
    if (newSegments.isEmpty) return;

    debugPrint('onSegmentReceived: ${newSegments.length} new segments, existing: ${segments.length}');

    if (segments.isEmpty) {
      audioStorage.removeFramesRange(fromSecond: 0, toSecond: newSegments[0].start.toInt());
    }
    streamStartedAtSecond ??= newSegments[0].start;

    var remainSegments = TranscriptSegment.updateSegments(segments, newSegments);
    TranscriptSegment.combineSegments(
      segments,
      remainSegments,
      toRemoveSeconds: streamStartedAtSecond ?? 0,
    );

    // Validate single speaker
    _validateSingleSpeaker();

    text = segments.map((e) => e.text).join(' ').trim();
    percentageCompleted = questionProgress;

    notifyInfo('SCROLL_DOWN');
    notifyListeners();
  }

  @override
  void onConnected() {}
}
