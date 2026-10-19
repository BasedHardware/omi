import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/siri_integration.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';
import 'package:omi/services/experiments/apple_speech_analyzer_gate.dart';
import 'package:omi/services/sockets/on_device_apple_provider.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/hard_secret_detector.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'guided_voice_controller.dart';
import 'guided_voice_requests.dart';

class DeviceGuidedVoiceIO implements GuidedVoiceIO, GuidedVoiceExperienceIO {
  DeviceGuidedVoiceIO({
    Future<Memory?> Function(String, String, String)? createMemoryRequest,
    IMicRecorderService? mic,
  })  : _createMemoryRequest = createMemoryRequest ?? createMemoryServer,
        _mic = mic;

  final Future<Memory?> Function(String, String, String) _createMemoryRequest;
  final IMicRecorderService? _mic;
  IMicRecorderService get _recorder => _mic ?? ServiceManager.instance().mic;
  bool _local = false;
  bool _selectionLocked = false;
  bool _recording = false;
  bool _closed = false;
  // Engine choice resolved once by preflight and injected into the recognizer
  // created by prepare(), so a flag change mid-session cannot make the provider
  // transcribe with a different engine than availability validated.
  bool? _useSpeechAnalyzer;
  // Non-null while a start() call is awaiting the recorder's own start-up. A stop()
  // that lands in this window can't stop a recorder that isn't running yet, so it
  // defers to start(): once the recorder comes up, start() sees _recording is false
  // and stops it immediately instead of leaving it running with no owner.
  Future<void>? _starting;
  String _language = 'en';
  OnDeviceAppleProvider? _recognizer;
  Directory? _directory;
  int _fileIndex = 0;
  int? _goalGeneration;

  @override
  bool get livePreview => _local;

  @override
  Future<bool> preflight() async {
    final prefs = SharedPreferencesUtil();
    _language = prefs.hasSetPrimaryLanguage ? prefs.userPrimaryLanguage : 'en';
    if (_language == 'multi') _language = 'en';
    // Resolve the engine gate once here; the provider created in prepare()
    // reuses this exact choice instead of re-reading the flag per operation.
    final analyzer = Platform.isIOS ? await AppleSpeechAnalyzerGate.useNewEngine() : true;
    final local = Platform.isIOS &&
        await OnDeviceAppleProvider.isOnDeviceAvailable(_language, useSpeechAnalyzer: () async => analyzer);
    // A slow preflight may finish after recording has been allowed. Never
    // switch its engine after prepare selected the recognizer/cloud path.
    if (!_selectionLocked && !_closed) {
      _local = local;
      _useSpeechAnalyzer = analyzer;
    }
    return _local || await guidedVoicePreflight();
  }

  @override
  Future<String> ask(String question, List<String> savedAnswers) async {
    return askGuidedPayoff(question, savedAnswers, onAccepted: () {
      PlatformManager.instance.analytics.chatMessageSent(
        message: question,
        includesFiles: false,
        numberOfFiles: 0,
        chatTargetId: 'omi',
        isPersonaChat: false,
        isVoiceInput: false,
      );
    });
  }

  @override
  Future<void> prepare() async {
    _selectionLocked = true;
    final permission = await Permission.microphone.request();
    if (!permission.isGranted) {
      throw GuidedVoiceFailure(permission.isPermanentlyDenied ? 'permission_permanently_denied' : 'permission_denied');
    }
    // Keep the language/engine selected by preflight: changing to cloud here
    // would start a recording without checking that transcription path. The
    // pinned engine choice is injected so transcribe() never re-reads the
    // flag and diverges from what availability validated.
    if (_local) {
      _recognizer = OnDeviceAppleProvider(
        language: _language,
        useSpeechAnalyzer: () async => _useSpeechAnalyzer ?? true,
      );
    }
    _directory = await (await getTemporaryDirectory()).createTemp('omi-introduction-');
    if (_closed) await close();
  }

  @override
  Future<void> start(void Function(Uint8List) onAudio, VoidCallback onInterrupted) async {
    if (_closed) return;
    _recording = true;
    final starting = _recorder.start(
      onByteReceived: onAudio,
      onStalled: onInterrupted,
      onInterruption: (began) {
        if (began) onInterrupted();
      },
    );
    _starting = starting;
    try {
      await starting;
    } catch (_) {
      _starting = null;
      _recording = false;
      rethrow;
    }
    _starting = null;
    if (!_recording) {
      // A stop() arrived while we were starting up; finish the job it couldn't.
      _recorder.stop();
      return;
    }
    PlatformManager.instance.analytics.speechProfileCapturePageClicked();
  }

  @override
  Future<void> stop() async {
    if (!_recording) return;
    _recording = false;
    if (_starting != null) return;
    _recorder.stop();
  }

  Uint8List _wav(Uint8List pcm) => WavBytes.fromPcm(pcm, sampleRate: 16000, numChannels: 1).asBytes();

  Future<File> _file(Uint8List pcm) async {
    final directory = _directory ??= await (await getTemporaryDirectory()).createTemp('omi-introduction-');
    return File('${directory.path}/${_fileIndex++}.wav').writeAsBytes(_wav(pcm));
  }

  @override
  Future<String> transcribe(Uint8List pcm) async {
    String text;
    if (_local) {
      text = (await _recognizer!.transcribe(_wav(pcm), language: _language).timeout(const Duration(seconds: 25)))
              ?.rawText ??
          '';
    } else {
      final file = await _file(pcm);
      try {
        text = await transcribeGuidedAnswer(file, _language);
      } finally {
        if (await file.exists()) await file.delete();
      }
    }
    // Reuse the capture hard-secret boundary; never turn credentials into a draft.
    return HardSecretDetector.contains(text) ? '' : text;
  }

  @override
  Future<bool> enroll(Uint8List pcm) async {
    final file = await _file(pcm);
    try {
      final saved = await uploadProfile(file).timeout(const Duration(seconds: 30));
      if (saved && !_closed) {
        SharedPreferencesUtil().hasSpeakerProfile = true;
        PlatformManager.instance.analytics.speechProfileUploadSucceeded();
        PlatformManager.instance.analytics.speechProfileEmbeddingStored();
      }
      return saved;
    } on SpeechProfileUploadException catch (e) {
      PlatformManager.instance.analytics.speechProfileUploadFailed(
        reason: 'http_${e.statusCode}',
        statusCode: e.statusCode,
      );
      if (e.statusCode == 503) throw VoiceEnrollmentUnavailable();
      rethrow;
    } catch (_) {
      PlatformManager.instance.analytics.speechProfileUploadFailed(reason: 'guided_upload_failed');
      rethrow;
    } finally {
      if (await file.exists()) await file.delete();
    }
  }

  @override
  Future<bool> remember(String text) async {
    if (HardSecretDetector.contains(text)) return false;
    // The canonical create endpoint derives the memory identity from content;
    // retries keep the same confirmed content and successful answers are skipped.
    final memory = await _createMemoryRequest(text, 'private', 'system').timeout(const Duration(seconds: 30));
    if (memory == null) return false;
    SiriIntegration.current.queueUpsertMemories([memory]);
    return true;
  }

  @override
  Future<bool> saveGoal(String text, String idempotencyKey) async {
    if (HardSecretDetector.contains(text) || text.isEmpty || text.length > 500) return false;
    _goalGeneration ??= AccountCutoverRuntime.instance.control.accountGeneration;
    return await createIntroductionGoal(
          text: text,
          idempotencyKey: idempotencyKey,
          accountGeneration: _goalGeneration!,
        ) !=
        null;
  }

  @override
  Future<void> close() async {
    _closed = true;
    await stop();
    _recognizer?.dispose();
    final directory = _directory;
    if (directory != null && await directory.exists()) await directory.delete(recursive: true);
  }
}
