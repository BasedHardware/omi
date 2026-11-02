import 'dart:async';
import 'dart:math' as math;
import 'dart:io' show File;
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/speech_profile.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/audio/wav_bytes.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// What the first-run dictation became: the conversation Omi wrote from it, or (when Omi could not
/// make one in time, or judged it not worth keeping) just the words the reader said.
@immutable
class ActivationResult {
  const ActivationResult({
    required this.transcript,
    this.emoji = '',
    this.title = '',
    this.overview = '',
    this.tasks = const [],
    this.notesPending = false,
  });

  final String transcript;
  final String emoji;
  final String title;
  final String overview;
  final List<String> tasks;

  /// Omi had not finished its notes when the reader was moved on; they land on Home later.
  final bool notesPending;

  /// Omi wrote notes from it; otherwise only [transcript] is shown.
  bool get hasNotes => title.isNotEmpty || overview.isNotEmpty;
}

/// How starting to listen went.
enum ActivationStart {
  listening,

  /// The reader's Omi is not streaming and the phone microphone is not allowed yet: ask for it first.
  needsMicrophone,
  failed,
}

/// The recording behind the first-run "Tell Omi about your day" step.
///
/// Uses the app's own capture pipeline, so the dictation becomes a real conversation that is first
/// on Home: through the reader's Omi when it is already streaming, otherwise through the phone
/// microphone. Replaceable in tests.
abstract class ActivationCapture {
  /// Whether the words come from the reader's Omi (true) or the phone microphone.
  bool get usesDevice;

  /// What has been heard since [start], updated live.
  ValueListenable<String> get liveText;

  /// How loud the audio coming in is, 0–1, updated live: Omi visibly hears the person before any
  /// words come back.
  ValueListenable<double> get level;

  /// Starts listening.
  Future<ActivationStart> start();

  /// Stops listening and waits (up to [timeout]) for Omi's notes.
  Future<ActivationResult> finish({Duration timeout});

  /// Stops listening without making notes.
  Future<void> cancel();
}

class PipelineActivationCapture implements ActivationCapture {
  PipelineActivationCapture(BuildContext context, {this.expectDevice = false})
      : _capture = context.read<CaptureProvider>(),
        _conversations = context.read<ConversationProvider>(),
        _home = context.read<HomeProvider>();

  /// The reader connected an Omi: wait for it to stream rather than taking over with the phone.
  final bool expectDevice;

  final CaptureProvider _capture;
  final ConversationProvider _conversations;
  final HomeProvider _home;
  final ValueNotifier<String> _live = ValueNotifier('');
  final ValueNotifier<double> _level = ValueNotifier(0);
  int _startIndex = 0;
  bool _device = false;
  bool _phoneStarted = false;
  bool _listening = false;

  /// Set by [cancel]. [start] checks it after each wait, so a Skip while it is still starting does
  /// not leave the phone microphone recording behind the next screen.
  bool _cancelled = false;

  /// When the dictation began, to tell its conversation from the audio before it.
  DateTime? _listeningSince;

  /// The phone dictation's own audio, kept to enroll the reader's voice (the old voice step did this;
  /// without it Omi cannot tell the reader apart from the people they talk to).
  final BytesBuilder _voice = BytesBuilder(copy: false);

  // 16 kHz mono PCM16. The server takes 5–180 s; a few sentences is plenty.
  static const _bytesPerSecond = 16000 * 2;
  static const _minVoiceSeconds = 6;

  /// Words the reader must have said for the audio to be worth a voiceprint: silence, a TV or
  /// someone else talking makes few or no words of the reader's own.
  static const _minVoiceWords = 10;
  static const _maxVoiceSeconds = 170;

  @override
  bool get usesDevice => _device;

  @override
  ValueListenable<String> get liveText => _live;

  @override
  ValueListenable<double> get level => _level;

  /// Eases toward [target] so the meter moves with speech without flickering.
  void _meter(double target) {
    final next = _level.value * 0.6 + target.clamp(0.0, 1.0) * 0.4;
    if ((next - _level.value).abs() > 0.01) _level.value = next;
  }

  /// Loudness of 16-bit little-endian PCM: speech sits roughly between 500 and 6000 RMS.
  static double _pcmLevel(List<int> pcm) {
    var sum = 0.0;
    var n = 0;
    for (var i = 0; i + 1 < pcm.length; i += 2) {
      var v = pcm[i] | (pcm[i + 1] << 8);
      if (v >= 0x8000) v -= 0x10000;
      sum += v * v;
      n++;
    }
    if (n == 0) return 0;
    return ((math.sqrt(sum / n) - 300) / 4000).clamp(0.0, 1.0);
  }

  /// The pendant's packets are compressed: louder speech makes bigger packets, silence small ones.
  static double _packetLevel(List<int> packet) => ((packet.length - 30) / 110).clamp(0.0, 1.0);

  void _onCapture() {
    if (!_listening) return;
    final segments = _capture.segments;
    // Fewer segments than when we started means the conversation was reset: all of them are new.
    if (segments.length < _startIndex) _startIndex = 0;
    final start = _startIndex;
    _live.value = segments.skip(start).map((s) => s.text.trim()).where((t) => t.isNotEmpty).join(' ');
  }

  @override
  Future<ActivationStart> start() async {
    try {
      // Live words need the streaming transport, not "transcribe later".
      await _capture.suspendBatchModeForOnboarding();
      // A just-connected Omi can take a moment to start streaming.
      for (var waited = 0; expectDevice && !_isDeviceRecording && waited < 5000; waited += 250) {
        await Future<void>.delayed(const Duration(milliseconds: 250));
        if (_cancelled) return ActivationStart.failed;
      }
      if (_cancelled) return ActivationStart.failed;
      _device = _isDeviceRecording;
      if (_device) {
        _capture.deviceAudioTap = (packet) => _meter(_packetLevel(packet));
        // The Omi has been listening since it connected (unboxing, the screens before this one).
        // Close that first, so the dictation is a conversation of its own.
        if (_capture.segments.isNotEmpty) await _capture.forceProcessingCurrentConversation();
      } else {
        if (!await Permission.microphone.isGranted) return ActivationStart.needsMicrophone;
        if (_cancelled) return ActivationStart.failed;
        _phoneStarted = true;
        final keepVoice = !SharedPreferencesUtil().hasSpeakerProfile;
        _capture.phoneMicAudioTap = (pcm) {
          _meter(_pcmLevel(pcm));
          if (keepVoice && _voice.length < _maxVoiceSeconds * _bytesPerSecond) _voice.add(pcm);
        };
        await _capture.streamRecording();
        // Skipped while the microphone was starting: cancel()'s stop may have run before it was on,
        // so stop it again now that it is.
        if (_cancelled) {
          _phoneStarted = true;
          await _stopPhone();
          return ActivationStart.failed;
        }
      }
      if (_cancelled) return ActivationStart.failed;
      _capture.suppressShortCaptureNotice = true;
      _startIndex = _capture.segments.length;
      _listeningSince = DateTime.now();
      _listening = true;
      _capture.addListener(_onCapture);
      return ActivationStart.listening;
    } catch (e) {
      Logger.debug('Activation capture could not start: $e');
      return ActivationStart.failed;
    }
  }

  bool get _isDeviceRecording => _capture.recordingState == RecordingState.deviceRecord;

  static final _word = RegExp(r"[\p{L}\p{N}']+", unicode: true);

  static Iterable<String> _wordsOf(String text) => _word.allMatches(text.toLowerCase()).map((m) => m.group(0)!);

  /// Whether [conversation] holds the dictation. The audio from before it (the unboxing, the screens
  /// before this one) can become a conversation in the same moment, so: it must not have begun well
  /// before the dictation, and its transcript must share most of the reader's first real words
  /// (whole words; "a", "to" and the like match anything).
  bool _isDictation(ServerConversation conversation, String heard) {
    final began = conversation.startedAt;
    final since = _listeningSince;
    // Server and phone clocks can differ a little; the earlier audio began minutes before.
    if (began != null && since != null && began.isBefore(since.subtract(const Duration(seconds: 20)))) {
      return false;
    }
    final words = _wordsOf(heard).where((w) => w.length > 2).take(6).toList();
    if (words.isEmpty) return true;
    final said = _wordsOf(conversation.transcriptSegments.map((s) => s.text).join(' ')).toSet();
    // Not loaded with the list: trust it only when its start time says it is the dictation.
    if (said.isEmpty) return began != null && since != null;
    return words.where(said.contains).length >= (words.length / 2).ceil();
  }

  void _stopListening() {
    _listening = false;
    _capture.removeListener(_onCapture);
    _capture.phoneMicAudioTap = null;
    _capture.deviceAudioTap = null;
    _capture.suppressShortCaptureNotice = false;
    _level.value = 0;
  }

  /// Uploads the dictation as the reader's voice profile, in the background: it never holds up the
  /// notes, and a failure only means the Home card or Settings asks for it later.
  Future<void> _enrollVoice(Uint8List pcm, String heard) async {
    if (pcm.length < _minVoiceSeconds * _bytesPerSecond || SharedPreferencesUtil().hasSpeakerProfile) return;
    if (_wordsOf(heard).length < _minVoiceWords) return;
    File? file;
    try {
      final directory = await getTemporaryDirectory();
      file = await File('${directory.path}/omi-first-voice-${DateTime.now().millisecondsSinceEpoch}.wav')
          .writeAsBytes(WavBytes.fromPcm(pcm, sampleRate: 16000, numChannels: 1).asBytes());
      if (await uploadProfile(file).timeout(const Duration(seconds: 45))) {
        SharedPreferencesUtil().hasSpeakerProfile = true;
        _home.setSpeakerProfile(true);
        PlatformManager.instance.analytics.speechProfileUploadSucceeded();
        PlatformManager.instance.analytics.speechProfileEmbeddingStored();
      }
    } on SpeechProfileUploadException catch (e) {
      PlatformManager.instance.analytics.speechProfileUploadFailed(
        reason: 'http_${e.statusCode}',
        statusCode: e.statusCode,
      );
    } catch (e) {
      Logger.debug('Activation voice enrollment failed: $e');
      PlatformManager.instance.analytics.speechProfileUploadFailed(reason: 'activation_upload_failed');
    } finally {
      if (file != null && await file.exists()) await file.delete();
    }
  }

  @override
  Future<ActivationResult> finish({Duration timeout = const Duration(seconds: 30)}) async {
    final transcript = _live.value;
    _stopListening();
    final known = _conversations.conversations.map((c) => c.id).toSet();
    final created = Completer<ServerConversation>();
    void watch() {
      for (final conversation in _conversations.conversations) {
        if (conversation.id == OptimisticProcessingPlaceholder.id || known.contains(conversation.id)) continue;
        // The audio from before the dictation may land here too; only the dictation's own counts.
        if (!_isDictation(conversation, transcript)) {
          known.add(conversation.id);
          continue;
        }
        if (!created.isCompleted) created.complete(conversation);
        return;
      }
    }

    _conversations.addListener(watch);
    try {
      if (_phoneStarted) {
        // If an Omi is connected but was not streaming, give it back the recording.
        await _capture.stopStreamRecording(resumeHandedOffPendant: expectDevice);
        _phoneStarted = false;
      }
      unawaited(_enrollVoice(_voice.takeBytes(), transcript));
      // Ends the conversation now instead of after the usual silence, and adds it to Home.
      await _capture.forceProcessingCurrentConversation();
      final conversation = await created.future.timeout(timeout);
      final structured = conversation.structured;
      if (conversation.discarded) return ActivationResult(transcript: transcript);
      return ActivationResult(
        transcript: transcript,
        emoji: '${structured.getEmoji()}',
        title: structured.title.trim(),
        overview: structured.overview.trim(),
        tasks: structured.actionItems
            .where((a) => !a.deleted)
            .map((a) => a.description.trim())
            .where((d) => d.isNotEmpty)
            .take(4)
            .toList(),
      );
    } catch (e) {
      Logger.debug('Activation notes not ready: $e');
      return ActivationResult(transcript: transcript);
    } finally {
      _conversations.removeListener(watch);
    }
  }

  @override
  Future<void> cancel() async {
    _cancelled = true;
    _stopListening();
    _voice.clear();
    await _stopPhone();
  }

  Future<void> _stopPhone() async {
    if (!_phoneStarted) return;
    _phoneStarted = false;
    try {
      await _capture.stopStreamRecording(resumeHandedOffPendant: expectDevice);
    } catch (_) {}
  }
}

/// Debug-only stand-in for local servers without speech-to-text: "hears" [script] word by word and
/// returns sample notes, so the activation can be reviewed end to end. Turn on with
/// `--dart-define=OMI_ACTIVATION_DEMO=1`, or `=device` to also act as if an Omi were connected
/// (simulators have no Bluetooth). Never active in release builds.
class DemoActivationCapture implements ActivationCapture {
  DemoActivationCapture({required this.script, required this.result});

  static const _flag = String.fromEnvironment('OMI_ACTIVATION_DEMO');
  static bool get enabled => kDebugMode && (_flag == '1' || _flag == 'device');

  /// Review the device owner's path without a device.
  static bool get pretendsDevice => kDebugMode && _flag == 'device';

  final String script;
  final ActivationResult result;
  final ValueNotifier<String> _live = ValueNotifier('');
  final ValueNotifier<double> _level = ValueNotifier(0);
  Timer? _timer;
  int _beat = 0;

  @override
  bool get usesDevice => pretendsDevice;

  @override
  ValueListenable<String> get liveText => _live;

  @override
  ValueListenable<double> get level => _level;

  @override
  Future<ActivationStart> start() async {
    final words = script.split(' ');
    var shown = 0;
    _timer = Timer.periodic(const Duration(milliseconds: 260), (timer) {
      if (shown >= words.length) {
        _level.value = 0;
        return timer.cancel();
      }
      shown++;
      _live.value = words.take(shown).join(' ');
      // A speaking rhythm for the meter.
      _level.value = 0.35 + 0.5 * ((_beat++ * 7) % 10) / 10;
    });
    return ActivationStart.listening;
  }

  @override
  Future<ActivationResult> finish({Duration timeout = const Duration(seconds: 30)}) async {
    _timer?.cancel();
    await Future<void>.delayed(const Duration(seconds: 2));
    return ActivationResult(
      transcript: _live.value,
      emoji: result.emoji,
      title: result.title,
      overview: result.overview,
      tasks: result.tasks,
    );
  }

  @override
  Future<void> cancel() async => _timer?.cancel();
}
