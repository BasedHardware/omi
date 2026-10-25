import 'dart:async';
import 'dart:collection';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/live_preview/local_preview_admission.dart';

/// What the live transcript surface shows for an admitted local-preview session.
enum LivePreviewPhase {
  /// Not admitted: the surface shows today's cloud live transcript.
  inactive,

  /// Admitted; the on-device engine is being selected and started.
  starting,

  /// An on-device engine runs. [LivePreviewController.lines] may still be empty.
  streaming,

  /// Admitted, but this phone has no usable on-device engine: calm "Transcribing…".
  unavailable,
}

@immutable
class LivePreviewLine {
  const LivePreviewLine({required this.id, required this.text, required this.isFinal});

  final String id;
  final String text;

  /// False while the recognizer may still revise the words (volatile).
  final bool isFinal;
}

/// Display-only on-device preview for mobile local-preview sessions.
///
/// It is deliberately a separate model from CaptureController.segments: preview
/// text never reaches LocalSegmentStore, the in-progress REST poll, the segment
/// arrival ledger used for WAL retention, or conversation creation. Audio is a
/// decoded COPY taken off the capture taps; the BLE/mic path only enqueues
/// into a bounded queue, and on overload preview audio is dropped, never capture
/// audio.
class LivePreviewController extends ChangeNotifier {
  LivePreviewController({
    required LivePreviewEngine engine,
    required this.telemetry,
    required this.platform,
    required this.osMajor,
    DateTime Function()? now,
    Duration Function()? conversationGap,
    List<int> Function(Uint8List opus)? decodeOpus,
    Future<bool> Function()? requestAllowed,
    this.maxLines = 200,
    this.maxQueuedPackets = 64,
    this.maxInFlightFeeds = 4,
    this.feedChunkBytes = 3200,
    this.maxPacketsPerTurn = 8,
  })  : _engine = engine,
        _now = now ?? DateTime.now,
        _conversationGap = conversationGap ?? (() => const Duration(minutes: 2)),
        _decodeOpus = decodeOpus,
        _requestAllowed = requestAllowed ?? (() async => true);

  final LivePreviewEngine _engine;
  final LivePreviewTelemetry telemetry;
  final LivePreviewPlatform platform;

  /// OS major version for telemetry; Android resolves it after composition.
  int osMajor;
  final DateTime Function() _now;
  final Duration Function() _conversationGap;
  final List<int> Function(Uint8List opus)? _decodeOpus;
  final Future<bool> Function() _requestAllowed;
  final int maxLines;
  final int maxQueuedPackets;
  final int maxInFlightFeeds;
  final int feedChunkBytes;

  /// Packets decoded per event-loop turn before yielding.
  final int maxPacketsPerTurn;

  LivePreviewPhase _phase = LivePreviewPhase.inactive;
  LivePreviewPhase get phase => _phase;
  bool get admitted => _phase != LivePreviewPhase.inactive;

  final List<LivePreviewLine> _lines = [];
  late final UnmodifiableListView<LivePreviewLine> _linesView = UnmodifiableListView(_lines);
  List<LivePreviewLine> get lines => _linesView;

  /// The newest non-empty preview line, for the home capture card's last-line slot.
  String? get latestLine {
    for (final line in _lines.reversed) {
      final text = line.text.trim();
      if (text.isNotEmpty) return text;
    }
    return null;
  }

  LivePreviewStart? _start;
  LivePreviewStart? get selected => _start;

  int _generation = 0;
  Future<void> _serial = Future.value();
  StreamSubscription<LivePreviewResult>? _results;
  DateTime? _lastResultAt;

  // Audio feed (bounded, preview-only).
  final Queue<_PreviewAudio> _queue = Queue();
  bool _drainScheduled = false;
  final BytesBuilder _pending = BytesBuilder(copy: false);
  int _inFlight = 0;

  // Per-session telemetry.
  DateTime? _firstAudioAt;
  bool _firstWordSent = false;
  int _fedBytes = 0;
  int _droppedBytes = 0;
  int _droppedPackets = 0;
  final Map<String, int> _finalWordCounts = {};

  int get droppedPacketsForTesting => _droppedPackets;
  int get queuedPacketsForTesting => _queue.length;

  /// One verdict measurement per declaring socket (observational).
  void reportVerdict(LocalPreviewVerdictReport report) => telemetry.verdict(report, platform: platform);

  String? _lastNotRequested;

  /// Reports a client-side refusal once per capture and reason.
  void clientRefused(String reasonWireName, {required bool midSession}) {
    final key = '$reasonWireName/$midSession';
    if (_lastNotRequested == key) return;
    _lastNotRequested = key;
    telemetry.notRequested(reasonWireName, midSession: midSession);
  }

  /// Whether this client may declare `local_preview=enabled` (kill switch).
  Future<bool> requestAllowed() => _requestAllowed();

  /// The server admitted this socket session. Starts (or keeps) the engine.
  void admit({required String language}) {
    if (_phase != LivePreviewPhase.inactive) return;
    final generation = ++_generation;
    _language = language;
    _failedEngines.clear();
    _phase = LivePreviewPhase.starting;
    notifyListeners();
    _startEngine(generation);
  }

  String _language = 'multi';

  /// Engines that failed at runtime in this admitted session. One fallback to
  /// the next engine is allowed; a second failure is the no-engine state.
  final Set<LivePreviewEngineKind> _failedEngines = {};

  void _startEngine(int generation) {
    _serial = _serial.then((_) async {
      if (generation != _generation) return;
      final start = await _engine.start(_language, exclude: Set.of(_failedEngines));
      if (generation != _generation) {
        if (start.running) await _engine.stop();
        return;
      }
      _start = start;
      _resetSessionTelemetry();
      telemetry.engineSelected(start, platform: platform, osMajor: osMajor);
      if (start.running) {
        _results = _engine.results.listen(_onResult, onError: (Object error) => _onRuntimeFailure(generation, error));
        _phase = LivePreviewPhase.streaming;
      } else {
        _phase = LivePreviewPhase.unavailable;
      }
      notifyListeners();
    });
  }

  /// The running engine died: close its run, then try the next engine once;
  /// otherwise settle in the calm no-engine state. Lines already shown stay.
  void _onRuntimeFailure(int generation, Object error) {
    final failed = _start;
    if (generation != _generation || failed == null || !failed.running) return;
    _failedEngines.add(failed.engine);
    _stopEngine();
    if (_failedEngines.length > 1) {
      _phase = LivePreviewPhase.unavailable;
      telemetry.engineSelected(const LivePreviewStart.none(LivePreviewReason.engineError),
          platform: platform, osMajor: osMajor);
      notifyListeners();
      return;
    }
    _startEngine(generation);
  }

  /// Admission ended (socket closed, server revoked, reconnecting). Lines are
  /// kept so a quick re-admission within the same capture continues them.
  void revoke() {
    if (_phase == LivePreviewPhase.inactive) return;
    _generation++;
    _phase = LivePreviewPhase.inactive;
    _stopEngine();
    notifyListeners();
  }

  /// The capture ended (stop, account change, dispose): the record replaces the
  /// preview through the conversation list's normal refresh, so drop it all.
  void endCapture() {
    final hadState = _phase != LivePreviewPhase.inactive || _lines.isNotEmpty;
    _generation++;
    _phase = LivePreviewPhase.inactive;
    _stopEngine();
    _lines.clear();
    _lastResultAt = null;
    _lastNotRequested = null;
    if (hadState) notifyListeners();
  }

  void _stopEngine() {
    final start = _start;
    _start = null;
    final results = _results;
    _results = null;
    _queue.clear();
    _pending.clear();
    if (start != null && start.running) {
      telemetry.sessionEnded(
        start.engine,
        previewWords: _finalWordCounts.values.fold(0, (sum, count) => sum + count),
        previewAudioMs: _fedBytes ~/ 32,
        // Queue/decoder drops are counted per packet (20 ms Opus frames).
        droppedAudioMs: _droppedBytes ~/ 32 + _droppedPackets * 20,
      );
    }
    _serial = _serial.then((_) async {
      await results?.cancel();
      if (start != null && start.running) await _engine.stop();
    });
  }

  void _resetSessionTelemetry() {
    _firstAudioAt = null;
    _firstWordSent = false;
    _fedBytes = 0;
    _droppedBytes = 0;
    _droppedPackets = 0;
    _finalWordCounts.clear();
  }

  // ---------------------------------------------------------------- audio --

  bool get _feeding => _phase == LivePreviewPhase.streaming && (_start?.running ?? false);

  /// Pendant tap: a raw BLE packet including its three-byte transport header.
  /// The packet is copied; capture's own bytes are never touched.
  void onPendantPacket(List<int> packet, BleAudioCodec codec) {
    if (!_feeding || packet.length <= 3) return;
    final isOpus = codec.isOpusSupported();
    if (!isOpus && codec != BleAudioCodec.pcm16) return;
    _enqueue(_PreviewAudio(Uint8List.fromList(packet.sublist(3)), opus: isOpus));
  }

  /// Phone-mic tap: PCM16 16 kHz mono.
  void onPhonePcm(List<int> pcm) {
    if (!_feeding || pcm.isEmpty) return;
    _enqueue(_PreviewAudio(Uint8List.fromList(pcm), opus: false));
  }

  void _enqueue(_PreviewAudio audio) {
    if (_queue.length >= maxQueuedPackets) {
      _droppedPackets++;
      return;
    }
    _queue.add(audio);
    _scheduleDrain();
  }

  /// Decode work runs on later event-loop turns (a timer, not a microtask), at
  /// most [maxPacketsPerTurn] packets per turn, so a burst never delays the
  /// next capture callback (BLE, mic, socket, WAL) by more than one bounded
  /// slice.
  void _scheduleDrain() {
    if (_drainScheduled) return;
    _drainScheduled = true;
    Timer.run(_drain);
  }

  void _drain() {
    _drainScheduled = false;
    var budget = maxPacketsPerTurn;
    while (_queue.isNotEmpty) {
      if (budget-- == 0) {
        _scheduleDrain();
        return;
      }
      final audio = _queue.removeFirst();
      if (!_feeding) continue;
      List<int> pcm;
      if (audio.opus) {
        try {
          pcm = _pcmBytes(_decode(audio.bytes));
        } catch (_) {
          _droppedPackets++;
          continue;
        }
      } else {
        pcm = audio.bytes;
      }
      _pending.add(pcm);
      if (_pending.length >= feedChunkBytes) _flush();
    }
  }

  List<int> _decode(Uint8List opus) {
    final decode = _decodeOpus;
    if (decode == null) throw StateError('No Opus decoder');
    return decode(opus);
  }

  static List<int> _pcmBytes(List<int> samples) {
    if (samples is Int16List) return samples.buffer.asUint8List(samples.offsetInBytes, samples.lengthInBytes);
    final out = Int16List(samples.length);
    for (var i = 0; i < samples.length; i++) {
      out[i] = samples[i];
    }
    return out.buffer.asUint8List();
  }

  void _flush() {
    final chunk = _pending.takeBytes();
    if (chunk.isEmpty) return;
    if (_inFlight >= maxInFlightFeeds) {
      _droppedBytes += chunk.length;
      return;
    }
    _firstAudioAt ??= _now();
    _inFlight++;
    final generation = _generation;
    _engine.feedPcm16(chunk).then((accepted) {
      if (generation != _generation) return;
      if (accepted) {
        _fedBytes += chunk.length;
      } else {
        _droppedBytes += chunk.length;
      }
    }).whenComplete(() => _inFlight--);
  }

  // -------------------------------------------------------------- results --

  void _onResult(LivePreviewResult result) {
    if (_phase != LivePreviewPhase.streaming) return;
    final now = _now();
    final text = result.text.trim();
    final last = _lastResultAt;
    if (text.isNotEmpty) {
      // A silence as long as the conversation timeout is a conversation
      // boundary: the earlier span becomes its own record, so stop showing it.
      if (last != null && now.difference(last) >= _conversationGap()) _lines.clear();
      _lastResultAt = now;
      _noteFirstWord(now);
    }
    final index = _lines.indexWhere((line) => line.id == result.segmentId);
    if (text.isEmpty) {
      if (index >= 0 && !_lines[index].isFinal) _lines.removeAt(index);
      if (result.isFinal) _finalWordCounts.remove(result.segmentId);
    } else {
      final line = LivePreviewLine(id: result.segmentId, text: text, isFinal: result.isFinal);
      if (index >= 0) {
        _lines[index] = line;
      } else {
        _lines.add(line);
        if (_lines.length > maxLines) _lines.removeRange(0, _lines.length - maxLines);
      }
      if (result.isFinal) _finalWordCounts[result.segmentId] = _wordCount(text);
    }
    notifyListeners();
  }

  void _noteFirstWord(DateTime now) {
    final firstAudio = _firstAudioAt;
    final start = _start;
    if (_firstWordSent || firstAudio == null || start == null) return;
    _firstWordSent = true;
    final latency = now.difference(firstAudio).inMilliseconds;
    telemetry.firstWord(start.engine, latencyMs: latency < 0 ? 0 : latency);
  }

  static int _wordCount(String text) => text.split(RegExp(r'\s+')).where((word) => word.isNotEmpty).length;

  @override
  void dispose() {
    endCapture();
    super.dispose();
  }
}

class _PreviewAudio {
  _PreviewAudio(this.bytes, {required this.opus});

  final Uint8List bytes;
  final bool opus;
}
