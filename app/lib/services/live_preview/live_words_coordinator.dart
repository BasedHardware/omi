import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_tail.dart';
import 'package:omi/services/live_preview/live_words_log.dart';
import 'package:omi/services/live_preview/vendor_live_words.dart';
import 'package:omi/utils/enums.dart';
import 'package:omi/utils/reliability_experiments.dart';

/// What the coordinator needs to know about capture, and the two things it asks of it. The capture
/// controller implements this; a test passes a fake.
abstract interface class LiveWordsCapture implements Listenable {
  RecordingState get recordingState;
  bool get isPaused;

  /// Seal the phone file being written, so the audio up to now uploads in the normal order.
  void sealOpenPhoneFile();

  /// The phone's recogniser runs because capture is active with the app in front (or no longer): the
  /// screens that show live words read this from capture and rebuild when it changes.
  void showLiveWordsInFront(bool value);
}

/// Reliability experiment `vendor_recognizer_on_opened_app`: decides when the live-words layer runs.
///
/// While capture is active (not paused, not stopped) and the app is exactly in front
/// (`AppLifecycleState.resumed`), the phone's own recogniser runs whether or not the server granted
/// the on-phone preview, and the vendor stream is open. When the app leaves the front, or capture is
/// paused or stopped, the vendor stream closes; the phone's recogniser keeps running only where the
/// server's grant already kept it. Coming to the front also seals the phone file being written, so
/// the stored transcript catches up sooner.
///
/// Off, this does nothing: no listener effect, no connection, no recogniser start.
class LiveWordsCoordinator {
  LiveWordsCoordinator({
    required this.capture,
    required this.preview,
    required this.vendor,
    bool Function()? enabled,
    bool Function()? cascade,
    String Function()? language,
    AppLifecycleState? Function()? lifecycleState,
    void Function(String event, Map<String, Object?> fields)? log,
    this.reportEvery = const Duration(seconds: 15),
  })  : _enabled = enabled ?? (() => ReliabilityExperiments.enabled(experiment)),
        _cascade = cascade ?? LivePreviewController.cascadeEnabled,
        _language = language ?? _preferredLanguage,
        _lifecycleState = lifecycleState ?? (() => WidgetsBinding.instance.lifecycleState),
        _log = log ?? ((event, fields) => LiveWordsLog.event(event, fields));

  static const experiment = 'vendor_recognizer_on_opened_app';

  final LiveWordsCapture capture;
  final LivePreviewController preview;
  final VendorLiveWords vendor;
  final Duration reportEvery;
  final bool Function() _enabled;
  final bool Function() _cascade;
  final String Function() _language;
  final AppLifecycleState? Function() _lifecycleState;
  final void Function(String event, Map<String, Object?> fields) _log;

  static String _preferredLanguage() {
    final preferences = SharedPreferencesUtil();
    return preferences.hasSetPrimaryLanguage ? preferences.userPrimaryLanguage : 'multi';
  }

  // Exactly `resumed`. A start in the background has no lifecycle state yet, and that is not "in front".
  bool _inFront = false;
  bool _syncing = false;
  bool _started = false;
  bool _wasActive = false;
  Timer? _report;

  bool get inFront => _inFront;

  void start() {
    if (_started) return;
    _started = true;
    _inFront = _lifecycleState() == AppLifecycleState.resumed;
    capture.addListener(sync);
    sync();
  }

  void dispose() {
    if (!_started) return;
    _started = false;
    capture.removeListener(sync);
    _report?.cancel();
    _report = null;
    vendor.dispose();
  }

  void onLifecycle(AppLifecycleState state) {
    final front = state == AppLifecycleState.resumed;
    if (front == _inFront) return;
    _inFront = front;
    if (front && _enabled() && _capturing) {
      // The app was opened: publish the audio up to now, so its stored text arrives sooner.
      capture.sealOpenPhoneFile();
    }
    sync();
  }

  bool get _capturing {
    if (capture.isPaused) return false;
    return switch (capture.recordingState) {
      RecordingState.deviceRecord ||
      RecordingState.record ||
      RecordingState.interrupted ||
      RecordingState.systemAudioRecord =>
        true,
      _ => false,
    };
  }

  /// Called on every capture change and lifecycle change. Cheap when nothing changed.
  void sync() {
    if (_syncing || !_started) return;
    _syncing = true;
    try {
      final on = _enabled();
      final capturing = on && _capturing;
      final active = capturing && _inFront;
      // Off, nothing below uses the language: skip the preference read on every capture change.
      final language = on ? _language() : 'multi';
      vendor.setState(capturing: capturing, inFront: active, language: language);
      preview.setFrontCapture(active, language: language);
      if (active != _wasActive) {
        _wasActive = active;
        _log('active', {
          'active': active,
          'capturing': capturing,
          'in_front': _inFront,
          'state': capture.recordingState.name,
          'paused': capture.isPaused,
        });
        _report?.cancel();
        _report = active ? Timer.periodic(reportEvery, (_) => _reportCounters()) : null;
        if (!active) _reportCounters();
      }
      capture.showLiveWordsInFront(preview.frontAdmitted);
    } finally {
      _syncing = false;
    }
  }

  /// Reliability experiment `live_words_cascade`: the person ended the conversation at [endedAt], the
  /// instant the End request carries. Returns the live words shown for the conversation being ended,
  /// as that request sends them (`live_tail`), then cuts the live words there, so every screen of the
  /// next conversation shows only words spoken after it, and tells the display connection, so the
  /// vendor's line in progress breaks at the same place. Off (or without the base experiment): null,
  /// and nothing is cut or sent.
  Map<String, Object?>? onEnd(DateTime endedAt) {
    if (!_started || !_enabled() || !_cascade()) return null;
    try {
      final tail = LiveTail.payload(preview.wordsUntil(endedAt), endedAt: endedAt);
      preview.cutAtEnd(endedAt);
      vendor.markEnd(endedAt);
      // Counts only: never a word.
      _log('end_cut', {
        'tail_words': LiveTail.wordCount(tail),
        'tail_lines': (tail?['lines'] as List?)?.length ?? 0,
        'vendor_connected': vendor.connected,
      });
      return tail;
    } catch (error) {
      // The End itself must go through whatever the live words do: it is then sent without a tail.
      _log('end_cut_failed', {'type': error.runtimeType.toString()});
      return null;
    }
  }

  void _reportCounters() {
    final cascade = _enabled() && _cascade();
    if (cascade) preview.settleCascadeCounters();
    _log('counters', {
      'own_phase': preview.phase.name,
      'own_results': preview.ownResultsHeard,
      'vendor_connected': vendor.connected,
      'vendor_sent_s': (vendor.totalSentMs / 1000).round(),
      'vendor_lines': vendor.linesReceived,
      'vendor_words': preview.vendorWordsSeen,
      if (cascade) ...{
        // What "filled" meant has no meaning once the vendor comes first.
        'cascade': true,
        'own_draft': preview.ownDraftAllowed(preview.language),
        'replaced_words': preview.vendorReplacedWords,
        'own_only_words': preview.ownOnlyWords,
        'neither_s': (preview.neitherMs / 1000).round(),
      } else ...{
        'filled_words': preview.vendorFilledWords,
        'filled_speech_ms': preview.vendorFilledSpeechMs,
      },
      'own_restarts': preview.watchdogRestarts,
      'dropped_connections': vendor.droppedConnections,
    });
  }
}
