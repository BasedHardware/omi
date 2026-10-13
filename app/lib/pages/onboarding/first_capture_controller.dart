import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';

enum FirstCapturePhase { ready, starting, recording, processing, result, empty, error, delayed }

abstract interface class FirstCaptureIO {
  String get transcript;
  Future<void> start();
  Future<ServerConversation?> finish();
  Future<void> cancel();
}

/// Owns only this guided attempt; the IO delegates capture and processing to Omi.
class FirstCaptureController extends ChangeNotifier {
  FirstCaptureController(this.io, {required this.emit, DateTime Function()? now}) : now = now ?? DateTime.now;
  final FirstCaptureIO io;
  final DateTime Function() now;
  DateTime? _startedAt;
  final void Function(RegisteredEvent) emit;
  FirstCapturePhase phase = FirstCapturePhase.ready;
  int seconds = 0;
  String transcript = '';
  bool transcriptObserved = false;
  ServerConversation? conversation;
  Timer? _timer;

  bool _disposed = false;
  bool _ownsRecording = false;
  int _attempt = 0;

  bool get canFinish => phase == FirstCapturePhase.recording && seconds >= 15;

  Future<void> start() async {
    if (phase == FirstCapturePhase.starting ||
        phase == FirstCapturePhase.recording ||
        phase == FirstCapturePhase.processing) {
      return;
    }
    final attempt = ++_attempt;
    phase = FirstCapturePhase.starting;
    seconds = 0;
    transcript = '';
    transcriptObserved = false;
    conversation = null;
    notifyListeners();
    try {
      await io.start();
      _ownsRecording = true;
      if (_disposed || attempt != _attempt) {
        await io.cancel();
        _ownsRecording = false;
        return;
      }
      phase = FirstCapturePhase.recording;
      _startedAt = now();
      emit(const OnboardingFirstCaptureRecordingStarted());
      _timer = Timer.periodic(const Duration(milliseconds: 250), (_) {
        seconds = now().difference(_startedAt!).inSeconds;
        transcript = io.transcript;
        transcriptObserved |= transcript.trim().isNotEmpty;
        notifyListeners();
        if (seconds >= 60) unawaited(finish());
      });
      notifyListeners();
    } catch (_) {
      if (_disposed || attempt != _attempt) return;
      phase = FirstCapturePhase.error;
      notifyListeners();
    }
  }

  Future<void> finish() async {
    if (!canFinish) return;
    final attempt = _attempt;
    _timer?.cancel();

    seconds = now().difference(_startedAt!).inSeconds;
    transcript = io.transcript;
    transcriptObserved |= transcript.trim().isNotEmpty;
    phase = FirstCapturePhase.processing;
    emit(OnboardingFirstCaptureRecordingCompleted(durationS: seconds, transcriptObserved: transcriptObserved));
    notifyListeners();
    final latency = Stopwatch()..start();
    try {
      final result = await io.finish().timeout(const Duration(seconds: 90));
      _ownsRecording = false;
      if (_disposed || attempt != _attempt) return;
      if (result == null && transcriptObserved) {
        // A 404 may mean websocket auto-finalization won the race; never call
        // an observed transcript "not enough speech" without its saved result.
        phase = FirstCapturePhase.delayed;
      } else if (result == null || result.discarded || result.transcriptSegments.isEmpty) {
        phase = FirstCapturePhase.empty;
        emit(const OnboardingFirstCaptureEmptyResult());
      } else {
        conversation = result;
        phase = FirstCapturePhase.result;
        emit(OnboardingFirstCaptureConversationShown(latencyMs: latency.elapsedMilliseconds));
      }
    } on TimeoutException {
      if (_disposed || attempt != _attempt) return;
      phase = FirstCapturePhase.delayed;
    } catch (_) {
      if (_disposed || attempt != _attempt) return;
      phase = FirstCapturePhase.error;
    }
    notifyListeners();
  }

  Future<void> leave() async {
    ++_attempt;
    _timer?.cancel();

    if (_ownsRecording) {
      await io.cancel();
      _ownsRecording = false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    unawaited(leave());
    super.dispose();
  }
}
