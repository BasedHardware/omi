import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';
import 'package:omi/services/sockets/on_device_apple_provider.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/hard_secret_detector.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'guided_voice_controller.dart';

class DeviceGuidedVoiceIO implements GuidedVoiceIO {
  bool _local = false;
  bool _recording = false;
  bool _closed = false;
  String _language = 'en';
  OnDeviceAppleProvider? _recognizer;
  Directory? _directory;
  int _fileIndex = 0;
  int? _goalGeneration;

  @override
  bool get livePreview => _local;

  @override
  Future<void> prepare() async {
    if (!await Permission.microphone.request().isGranted) throw StateError('microphone');
    final prefs = SharedPreferencesUtil();
    _language = prefs.hasSetPrimaryLanguage ? prefs.userPrimaryLanguage : 'en';
    if (_language == 'multi') _language = 'en';
    _local = Platform.isIOS && await OnDeviceAppleProvider.isOnDeviceAvailable(_language);
    if (_local) _recognizer = OnDeviceAppleProvider(language: _language);
    _directory = await (await getTemporaryDirectory()).createTemp('omi-introduction-');
    if (_closed) await close();
  }

  @override
  Future<void> start(void Function(Uint8List) onAudio, VoidCallback onInterrupted) async {
    if (_closed) return;
    _recording = true;
    try {
      await ServiceManager.instance().mic.start(
            onByteReceived: onAudio,
            onStalled: onInterrupted,
            onInterruption: (began) {
              if (began) onInterrupted();
            },
          );
      PlatformManager.instance.analytics.speechProfileCapturePageClicked();
    } catch (_) {
      _recording = false;
      rethrow;
    }
  }

  @override
  Future<void> stop() async {
    if (!_recording) return;
    _recording = false;
    ServiceManager.instance().mic.stop();
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
        text = await transcribeVoiceMessage([file], language: _language).timeout(const Duration(seconds: 30));
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
      PlatformManager.instance.analytics
          .speechProfileUploadFailed(reason: 'http_${e.statusCode}', statusCode: e.statusCode);
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
    return await createMemoryServer(text, 'private', 'system').timeout(const Duration(seconds: 30)) != null;
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
