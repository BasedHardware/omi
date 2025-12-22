import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api/onboarding.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/sockets/transcription_service.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:permission_handler/permission_handler.dart';

/// Represents a question for onboarding
class OnboardingQuestion {
  final String question;
  final String category;
  String? answer;
  bool isAnswered;

  OnboardingQuestion({
    required this.question,
    required this.category,
    this.answer,
    this.isAnswered = false,
  });

  Map<String, dynamic> toJson() => {
    'question': question,
    'answer': answer ?? '',
    'category': category,
  };
}

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
  
  // Question-based onboarding
  bool useQuestionMode = false;
  bool usePhoneMic = false; // Use phone microphone instead of Omi device
  static final List<OnboardingQuestion> defaultQuestions = [
    OnboardingQuestion(question: 'How old are you?', category: 'age'),
    OnboardingQuestion(question: 'Where do you live?', category: 'location'),
    OnboardingQuestion(question: 'What do you do for work?', category: 'work'),
    OnboardingQuestion(question: 'What is your long-term goal?', category: 'long_term_goal'),
    OnboardingQuestion(question: 'What are your goals this month?', category: 'monthly_goals'),
    OnboardingQuestion(question: 'What do you have planned for today?', category: 'daily_plans'),
  ];
  
  List<OnboardingQuestion> questions = [];
  int currentQuestionIndex = 0;
  String currentTranscriptForQuestion = '';
  Timer? _answerDetectionTimer;
  Timer? _silenceTimer;
  bool isProcessingAnswer = false;
  DateTime? _lastSegmentReceivedAt; // Track when last segment was received for silence detection
  
  String get currentQuestion => questions.isNotEmpty && currentQuestionIndex < questions.length 
      ? questions[currentQuestionIndex].question 
      : '';
  
  double get questionProgress => questions.isEmpty 
      ? 0.0 
      : (currentQuestionIndex / questions.length).clamp(0.0, 1.0);

  /////////////////////////////////

  void enableQuestionMode() {
    useQuestionMode = true;
    questions = defaultQuestions.map((q) => OnboardingQuestion(
      question: q.question,
      category: q.category,
    )).toList();
    currentQuestionIndex = 0;
    currentTranscriptForQuestion = '';
    notifyListeners();
  }

  CaptureProvider? _captureProvider;
  
  /// Enable question mode using CaptureProvider's transcription stream
  void enableQuestionModeWithCaptureProvider(CaptureProvider captureProvider) {
    useQuestionMode = true;
    usePhoneMic = true;
    _captureProvider = captureProvider;
    
    questions = defaultQuestions.map((q) => OnboardingQuestion(
      question: q.question,
      category: q.category,
    )).toList();
    currentQuestionIndex = 0;
    currentTranscriptForQuestion = '';
    _lastTranscriptLength = 0;
    
    // Listen to CaptureProvider's segments
    captureProvider.addListener(_onCaptureProviderUpdate);
    
    notifyListeners();
  }
  
  void _onCaptureProviderUpdate() {
    if (_captureProvider == null || !useQuestionMode) return;
    
    // Get segments from CaptureProvider
    final captureSegments = _captureProvider!.segments;
    if (captureSegments.isEmpty) return;
    
    // Update our transcript with CaptureProvider's segments
    currentTranscriptForQuestion = captureSegments.map((e) => e.text).join(' ').trim();
    text = currentTranscriptForQuestion;
    
    // Trigger answer detection
    _startAnswerDetection();
    
    notifyInfo('SCROLL_DOWN');
    notifyListeners();
  }
  
  /// Finalize question mode (without speech profile upload)
  Future<void> finalizeQuestionMode() async {
    if (uploadingProfile || profileCompleted) return;
    
    // Cancel timers
    _answerDetectionTimer?.cancel();
    _silenceTimer?.cancel();
    forceCompletionTimer?.cancel();
    
    // Remove listener
    _captureProvider?.removeListener(_onCaptureProviderUpdate);
    
    uploadingProfile = true;
    notifyListeners();
    
    updateLoadingText('Saving your goals...');
    
    // Create onboarding conversation with answered questions
    try {
      final answeredQuestions = questions
          .where((q) => q.isAnswered && q.answer != null && q.answer != 'Skipped')
          .map((q) => q.toJson())
          .toList();
      
      if (answeredQuestions.isNotEmpty) {
        conversation = await createOnboardingConversation(answeredQuestions);
        debugPrint('Onboarding conversation created: ${conversation?.id}');
      }
    } catch (e) {
      debugPrint('Error creating onboarding conversation: $e');
    }
    
    uploadingProfile = false;
    profileCompleted = true;
    text = '';
    updateLoadingText("You're all set!");
    notifyListeners();
  }

  int _lastTranscriptLength = 0;
  int _questionStartTranscriptLength = 0; // Track where each question's answer starts
  String _fullTranscript = ''; // Full transcript from beginning
  
  void _startAnswerDetection() {
    _silenceTimer?.cancel();
    _lastSegmentReceivedAt = DateTime.now();
    
    final currentLength = _fullTranscript.length;
    
    // Only start timer if transcript has grown (new speech detected)
    if (currentLength > _lastTranscriptLength) {
      _lastTranscriptLength = currentLength;
      
      // Calculate new text for current question only
      final newTextForQuestion = _fullTranscript.substring(_questionStartTranscriptLength).trim();
      currentTranscriptForQuestion = newTextForQuestion;
      text = newTextForQuestion;
      
      debugPrint('Answer detection: full transcript length=$currentLength, question start=$_questionStartTranscriptLength');
      debugPrint('Answer detection: new text for this question: "$newTextForQuestion"');
      
      // Start silence detection - if no new words for 5 seconds, check for answer
      _silenceTimer = Timer(const Duration(seconds: 5), () {
        debugPrint('Answer detection: 5s silence timer fired, checking answer...');
        if (currentTranscriptForQuestion.trim().isNotEmpty && !isProcessingAnswer) {
          _detectAnswerWithAI();
        }
      });
    }
  }

  Future<void> _detectAnswerWithAI() async {
    if (isProcessingAnswer) {
      debugPrint('Answer detection: already processing, skipping');
      return;
    }
    if (currentTranscriptForQuestion.trim().isEmpty) {
      debugPrint('Answer detection: transcript empty, skipping');
      return;
    }
    
    isProcessingAnswer = true;
    notifyListeners();
    
    final currentQuestion = questions[currentQuestionIndex].question;
    debugPrint('Answer detection: checking answer for question "$currentQuestion"');
    debugPrint('Answer detection: transcript = "$currentTranscriptForQuestion"');
    
    // Simple client-side answer detection: if user spoke at least 2 words, consider it answered
    final wordCount = currentTranscriptForQuestion.trim().split(RegExp(r'\s+')).where((s) => s.isNotEmpty).length;
    debugPrint('Answer detection: word count = $wordCount');
    
    if (wordCount >= 2) {
      debugPrint('Answer detection: User spoke $wordCount words. Moving to next question.');
      // Save the answer
      questions[currentQuestionIndex].answer = currentTranscriptForQuestion;
      questions[currentQuestionIndex].isAnswered = true;
      
      // Move to next question (this will reset all tracking)
      _moveToNextQuestion();
    } else {
      debugPrint('Answer detection: Not enough words ($wordCount), waiting for more input...');
      isProcessingAnswer = false;
      notifyListeners();
    }
  }

  void skipCurrentQuestion() {
    if (currentQuestionIndex < questions.length) {
      questions[currentQuestionIndex].answer = currentTranscriptForQuestion.isEmpty 
          ? 'Skipped' 
          : currentTranscriptForQuestion;
      questions[currentQuestionIndex].isAnswered = true;
      _moveToNextQuestion();
    }
  }

  void _moveToNextQuestion() {
    currentQuestionIndex++;
    currentTranscriptForQuestion = '';
    text = '';
    isProcessingAnswer = false;
    
    // IMPORTANT: Mark where the next question's answer starts in the full transcript
    // Don't clear segments - we want to keep the full audio for speech profile
    _questionStartTranscriptLength = _fullTranscript.length;
    _lastTranscriptLength = _fullTranscript.length;
    
    debugPrint('Moving to question ${currentQuestionIndex + 1} of ${questions.length}');
    debugPrint('Next question starts at transcript position: $_questionStartTranscriptLength');
    
    if (currentQuestionIndex >= questions.length) {
      // All questions answered - finalize
      debugPrint('All questions answered, finalizing...');
      finalize();
    } else {
      debugPrint('Next question: "${questions[currentQuestionIndex].question}"');
      notifyInfo('NEXT_QUESTION');
      notifyListeners();
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
    // Connect to the transcript socket
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
      
      // Cancel answer detection timers
      _answerDetectionTimer?.cancel();
      _silenceTimer?.cancel();

      if (!useQuestionMode) {
        // Original validation for non-question mode
        int duration = segments.isEmpty ? 0 : segments.last.end.toInt();
        if (duration < 10 || duration > 155) {
          if (percentageCompleted < 80) {
            notifyError('NO_SPEECH');
            return;
          }
        }

        String text = segments.map((e) => e.text).join(' ').trim();
        if (text.split(' ').length < (targetWordsCount / 2)) {
          // 25 words
          notifyError('TOO_SHORT');
          return;
        }
      }
      
      uploadingProfile = true;
      notifyListeners();
      
      // Stop phone mic streaming if using it
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
            return false; // Return false on timeout
          },
        );
        debugPrint('Profile upload completed');
      } catch (e) {
        debugPrint('Error uploading profile: $e');
      }

      SharedPreferencesUtil().hasSpeakerProfile = true;
      debugPrint('Speaker profile saved to preferences');
      
      // In question mode, create conversation and memories
      if (useQuestionMode) {
        updateLoadingText('Saving your goals...');
        try {
          final answeredQuestions = questions
              .where((q) => q.isAnswered && q.answer != null && q.answer != 'Skipped')
              .map((q) => q.toJson())
              .toList();
          
          if (answeredQuestions.isNotEmpty) {
            conversation = await createOnboardingConversation(answeredQuestions);
            debugPrint('Onboarding conversation created: ${conversation?.id}');
          }
        } catch (e) {
          debugPrint('Error creating onboarding conversation: $e');
        }
      }
      
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
    _answerDetectionTimer?.cancel();
    _silenceTimer?.cancel();
    
    // Stop phone mic streaming if using it
    _stopPhoneMicStreaming();
    
    // Remove CaptureProvider listener if any
    _captureProvider?.removeListener(_onCaptureProviderUpdate);
    _captureProvider = null;
    
    segments.clear();
    text = '';
    startedRecording = false;
    percentageCompleted = 0;
    uploadingProfile = false;
    profileCompleted = false;
    usePhoneMic = false;
    
    // Reset question mode state
    currentQuestionIndex = 0;
    currentTranscriptForQuestion = '';
    isProcessingAnswer = false;
    _lastTranscriptLength = 0;
    _questionStartTranscriptLength = 0;
    _fullTranscript = '';
    questions.clear();
    await _socket?.stop(reason: 'closing');
    notifyListeners();
  }

  @override
  void dispose() {
    // This won't be called unless the provider is removed from the widget tree. So we need to manually call this in the widget's dispose method.
    connectionStateListener?.cancel();
    _bleBytesStream?.cancel();
    forceCompletionTimer?.cancel();
    _answerDetectionTimer?.cancel();
    _silenceTimer?.cancel();
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
    // TODO: implement onClosed
  }

  @override
  void onError(Object err) {
    notifyError('WS_ERR');
  }

  @override
  void onMessageEventReceived(MessageEvent event) {
    // TODO: implement onMessageEventReceived
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
    
    if (useQuestionMode) {
      // In question mode, track full transcript and extract current question's portion
      _fullTranscript = segments.map((e) => e.text).join(' ').trim();
      
      // Extract only the text for the current question
      final newTextForQuestion = _fullTranscript.length > _questionStartTranscriptLength 
          ? _fullTranscript.substring(_questionStartTranscriptLength).trim()
          : '';
      currentTranscriptForQuestion = newTextForQuestion;
      text = newTextForQuestion;
      
      debugPrint('Question mode - full: ${_fullTranscript.length} chars, question text: "$newTextForQuestion"');
      
      // Trigger answer detection after silence
      _startAnswerDetection();
      
      // Update progress based on questions answered
      percentageCompleted = questionProgress;
    } else {
      // Original behavior
      updateProgressMessage();
      _validateSingleSpeaker();
      _handleCompletion();
    }
    
    notifyInfo('SCROLL_DOWN');
    notifyListeners();
    debugPrint('Conversation creation timer restarted');
  }

  @override
  void onConnected() {}
}
