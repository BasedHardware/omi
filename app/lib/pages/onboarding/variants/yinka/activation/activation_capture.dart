import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

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

  failed,
}

/// The recording behind the first-run "Tell Omi about your day" step.
///
abstract class ActivationCapture {
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
  PipelineActivationCapture(BuildContext context)
      : _capture = context.read<CaptureProvider>(),
        _conversations = context.read<ConversationProvider>();

  final CaptureProvider _capture;
  final ConversationProvider _conversations;
  final ValueNotifier<String> _live = ValueNotifier('');
  final ValueNotifier<double> _level = ValueNotifier(0);
  int _startIndex = 0;
  bool _listening = false;

  bool _cancelled = false;

  /// When the dictation began, to tell its conversation from the audio before it.
  DateTime? _listeningSince;

  @override
  ValueListenable<String> get liveText => _live;

  @override
  ValueListenable<double> get level => _level;

  /// Eases toward [target] so the meter moves with speech without flickering.
  void _meter(double target) {
    final next = _level.value * 0.6 + target.clamp(0.0, 1.0) * 0.4;
    if ((next - _level.value).abs() > 0.01) _level.value = next;
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
      for (var waited = 0; !_isDeviceRecording && waited < 5000; waited += 250) {
        await Future<void>.delayed(const Duration(milliseconds: 250));
        if (_cancelled) return ActivationStart.failed;
      }
      if (_cancelled) return ActivationStart.failed;
      if (!_isDeviceRecording) return ActivationStart.failed;
      // Close any earlier conversation before the first-run dictation.
      if (_capture.segments.isNotEmpty) await _capture.forceProcessingCurrentConversation();
      if (_cancelled) return ActivationStart.failed;
      _capture.deviceAudioTap = (packet) => _meter(_packetLevel(packet));
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
    _capture.deviceAudioTap = null;
    _capture.suppressShortCaptureNotice = false;
    _level.value = 0;
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
