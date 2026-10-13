import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import 'package:permission_handler/permission_handler.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/logger.dart';

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
  });

  final String transcript;
  final String emoji;
  final String title;
  final String overview;
  final List<String> tasks;

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
        _conversations = context.read<ConversationProvider>();

  /// The reader connected an Omi: wait for it to stream rather than taking over with the phone.
  final bool expectDevice;

  final CaptureProvider _capture;
  final ConversationProvider _conversations;
  final ValueNotifier<String> _live = ValueNotifier('');
  int _startIndex = 0;
  bool _device = false;
  bool _phoneStarted = false;
  bool _listening = false;

  @override
  bool get usesDevice => _device;

  @override
  ValueListenable<String> get liveText => _live;

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
      }
      _device = _isDeviceRecording;
      if (_device) {
        // The Omi has been listening since it connected (unboxing, the screens before this one).
        // Close that first, so the dictation is a conversation of its own.
        if (_capture.segments.isNotEmpty) await _capture.forceProcessingCurrentConversation();
      } else {
        if (!await Permission.microphone.isGranted) return ActivationStart.needsMicrophone;
        await _capture.streamRecording();
        _phoneStarted = true;
      }
      _startIndex = _capture.segments.length;
      _listening = true;
      _capture.addListener(_onCapture);
      return ActivationStart.listening;
    } catch (e) {
      Logger.debug('Activation capture could not start: $e');
      return ActivationStart.failed;
    }
  }

  bool get _isDeviceRecording => _capture.recordingState == RecordingState.deviceRecord;

  /// Whether [conversation] holds the dictation: its transcript starts with words the reader said.
  bool _isDictation(ServerConversation conversation, String heard) {
    final words = heard.toLowerCase().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).take(4).toList();
    if (words.isEmpty) return true;
    final transcript = conversation.transcriptSegments.map((s) => s.text).join(' ').toLowerCase();
    if (transcript.isEmpty) return true; // Not loaded with the list; the newest new one is ours.
    return words.where(transcript.contains).length >= (words.length / 2).ceil();
  }

  void _stopListening() {
    _listening = false;
    _capture.removeListener(_onCapture);
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
    _stopListening();
    if (_phoneStarted) {
      _phoneStarted = false;
      try {
        await _capture.stopStreamRecording(resumeHandedOffPendant: expectDevice);
      } catch (_) {}
    }
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
  Timer? _timer;

  @override
  bool get usesDevice => pretendsDevice;

  @override
  ValueListenable<String> get liveText => _live;

  @override
  Future<ActivationStart> start() async {
    final words = script.split(' ');
    var shown = 0;
    _timer = Timer.periodic(const Duration(milliseconds: 260), (timer) {
      if (shown >= words.length) return timer.cancel();
      shown++;
      _live.value = words.take(shown).join(' ');
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
