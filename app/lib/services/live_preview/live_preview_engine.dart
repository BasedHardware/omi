import 'dart:async';

import 'package:flutter/services.dart';

/// On-device engine that produced a session's live preview. Closed set; the
/// wire names are the telemetry and native channel values.
enum LivePreviewEngineKind {
  speechTranscriber('speech_transcriber'),
  sfSpeech('sf_speech'),
  androidOnDevice('android_on_device'),
  parakeet('parakeet'),
  whisper('whisper'),
  none('none');

  const LivePreviewEngineKind(this.wireName);
  final String wireName;

  static LivePreviewEngineKind parse(Object? value) =>
      values.firstWhere((kind) => kind.wireName == value, orElse: () => LivePreviewEngineKind.none);
}

/// Why a session has (or does not have) an on-device preview. Closed set.
enum LivePreviewReason {
  ok('ok'),
  notAdmitted('not_admitted'),
  killSwitch('kill_switch'),
  osTooOld('os_too_old'),
  osEngineUnavailable('os_engine_unavailable'),
  localeUnsupported('locale_unsupported'),
  localeAssetMissing('locale_asset_missing'),
  speechPermissionDenied('speech_permission_denied'),
  bundledNotInstalled('bundled_not_installed'),
  bundledNotBuilt('bundled_not_built'),
  engineError('engine_error');

  const LivePreviewReason(this.wireName);
  final String wireName;

  static LivePreviewReason parse(Object? value) =>
      values.firstWhere((reason) => reason.wireName == value, orElse: () => LivePreviewReason.engineError);
}

/// The engine chosen for one session. [engine] is [LivePreviewEngineKind.none]
/// whenever [reason] is not [LivePreviewReason.ok].
class LivePreviewStart {
  const LivePreviewStart(this.engine, this.reason, {this.bundledInstalled = false});

  const LivePreviewStart.none(this.reason)
      : engine = LivePreviewEngineKind.none,
        bundledInstalled = false;

  final LivePreviewEngineKind engine;
  final LivePreviewReason reason;

  /// Whether Omi's own downloadable on-device model is present on this phone.
  final bool bundledInstalled;

  bool get running => engine != LivePreviewEngineKind.none;

  factory LivePreviewStart.fromWire(Object? value) {
    if (value is! Map) return const LivePreviewStart.none(LivePreviewReason.engineError);
    final engine = LivePreviewEngineKind.parse(value['engine']);
    final reason = LivePreviewReason.parse(value['reason']);
    final bundled = value['bundledInstalled'] == true;
    if (engine == LivePreviewEngineKind.none || reason != LivePreviewReason.ok) {
      return LivePreviewStart(
          LivePreviewEngineKind.none, reason == LivePreviewReason.ok ? LivePreviewReason.engineError : reason,
          bundledInstalled: bundled);
    }
    return LivePreviewStart(engine, reason, bundledInstalled: bundled);
  }
}

/// One independently timed recognizer span (a word when the engine provides it).
class LivePreviewSpan {
  const LivePreviewSpan({required this.text, required this.startedAt, required this.endedAt});
  final String text;
  final DateTime startedAt;
  final DateTime endedAt;
}

/// One recognizer hypothesis. A volatile result is replaced by the next result
/// with the same [segmentId]; a final one is settled.
class LivePreviewResult {
  const LivePreviewResult(
      {required this.segmentId,
      required this.text,
      required this.isFinal,
      this.startedAt,
      this.endedAt,
      this.spans = const []});

  final String segmentId;
  final String text;
  final bool isFinal;

  /// Audio time, not result delivery time. Missing timing cannot prove coverage.
  final DateTime? startedAt;
  final DateTime? endedAt;
  final List<LivePreviewSpan> spans;

  static LivePreviewResult? fromWire(Object? value) {
    if (value is! Map) return null;
    final id = value['segmentId'];
    final text = value['text'];
    if (id is! String || id.isEmpty || text is! String) return null;
    DateTime? time(Object? ms) =>
        ms is num && ms.isFinite ? DateTime.fromMillisecondsSinceEpoch(ms.round(), isUtc: true) : null;
    return LivePreviewResult(
        segmentId: id,
        text: text,
        isFinal: value['isFinal'] == true,
        startedAt: time(value['startMs']),
        endedAt: time(value['endMs']),
        spans: [
          if (value['spans'] is List)
            for (final span in value['spans'] as List)
              if (span is Map && span['text'] is String && time(span['startMs']) != null && time(span['endMs']) != null)
                LivePreviewSpan(
                    text: span['text'] as String, startedAt: time(span['startMs'])!, endedAt: time(span['endMs'])!),
        ]);
  }
}

/// A running engine stopped working for good (closed reason: engine_error).
/// Delivered as an error on [LivePreviewEngine.results].
class LivePreviewRuntimeFailure implements Exception {
  const LivePreviewRuntimeFailure(this.engine);

  final LivePreviewEngineKind engine;
  LivePreviewReason get reason => LivePreviewReason.engineError;

  @override
  String toString() => 'LivePreviewRuntimeFailure(${engine.wireName})';
}

/// A display-only streaming recognizer fed 16 kHz mono PCM16. It never owns,
/// stores or uploads audio.
abstract interface class LivePreviewEngine {
  /// Selects and starts the best engine, skipping any in [exclude] (engines
  /// that already failed at runtime in this session).
  Future<LivePreviewStart> start(String language, {Set<LivePreviewEngineKind> exclude = const {}});

  /// Returns false when the engine refused or failed the chunk. Callers drop it.
  Future<bool> feedPcm16(Uint8List pcm, {DateTime? startedAt});

  Future<void> stop();

  /// Hypotheses; a [LivePreviewRuntimeFailure] error when the engine dies.
  Stream<LivePreviewResult> get results;
}

/// Native per-platform engine (iOS `LivePreviewPlugin.swift`). Deliberately a
/// separate channel from the single-flight `com.omi/on_device` overflow plugin.
class MethodChannelLivePreviewEngine implements LivePreviewEngine {
  MethodChannelLivePreviewEngine({MethodChannel? channel, EventChannel? events})
      : _channel = channel ?? const MethodChannel(methodChannelName),
        _events = events ?? const EventChannel(eventChannelName);

  static const methodChannelName = 'com.omi/live_preview';
  static const eventChannelName = 'com.omi/live_preview/events';

  final MethodChannel _channel;
  final EventChannel _events;
  Stream<LivePreviewResult>? _results;

  @override
  Stream<LivePreviewResult> get results => _results ??= _events.receiveBroadcastStream().transform(
        StreamTransformer<dynamic, LivePreviewResult>.fromHandlers(
          handleData: (event, sink) {
            if (event is Map && event['failure'] != null) {
              sink.addError(LivePreviewRuntimeFailure(LivePreviewEngineKind.parse(event['engine'])));
              return;
            }
            final result = LivePreviewResult.fromWire(event);
            if (result != null) sink.add(result);
          },
          // A broken event channel is a dead engine too.
          handleError: (error, stack, sink) =>
              sink.addError(const LivePreviewRuntimeFailure(LivePreviewEngineKind.none), stack),
        ),
      );

  @override
  Future<LivePreviewStart> start(String language, {Set<LivePreviewEngineKind> exclude = const {}}) async {
    try {
      return LivePreviewStart.fromWire(await _channel.invokeMethod<Object?>('start', {
        'language': language,
        if (exclude.isNotEmpty) 'exclude': [for (final engine in exclude) engine.wireName],
      }));
    } on MissingPluginException {
      // No native engine on this platform build yet.
      return const LivePreviewStart.none(LivePreviewReason.osEngineUnavailable);
    } catch (_) {
      return const LivePreviewStart.none(LivePreviewReason.engineError);
    }
  }

  @override
  Future<bool> feedPcm16(Uint8List pcm, {DateTime? startedAt}) async {
    try {
      return await _channel.invokeMethod<bool>(
              'feed', {'pcm': pcm, if (startedAt != null) 'startMs': startedAt.millisecondsSinceEpoch}) ??
          false;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> stop() async {
    try {
      await _channel.invokeMethod<void>('stop');
    } catch (_) {
      // Display-only: a failed stop never affects capture.
    }
  }
}
