import 'dart:async';
import 'dart:collection';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_notes.dart';
import 'package:omi/services/live_preview/live_preview_word_budget.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/live_preview/live_words_merge.dart';
import 'package:omi/services/live_preview/local_preview_admission.dart';
import 'package:omi/utils/reliability_experiments.dart';

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
  const LivePreviewLine(
      {required this.id,
      required this.text,
      required this.isFinal,
      this.startedAt,
      this.endedAt,
      this.firstSeenAt,
      this.spans = const []});

  final String id;
  final String text;

  /// False while the recognizer may still revise the words (volatile).
  final bool isFinal;
  final DateTime? startedAt;
  final DateTime? endedAt;

  /// First recognizer result time for this id, used only when audio timing is
  /// unavailable and the server's settled watermark eventually passes it.
  final DateTime? firstSeenAt;
  final List<LivePreviewSpan> spans;
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
    LivePreviewNotesEngine? notesEngine,
    DateTime Function()? now,
    Duration Function()? conversationGap,
    List<int> Function(Uint8List opus)? decodeOpus,
    Future<bool> Function()? requestAllowed,
    bool Function()? ownResultsMuted,
    bool Function()? retimeOwnResults,
    this.watchdogSilence = const Duration(seconds: 10),
    this.watchdogMinInterval = const Duration(minutes: 3),
    this.watchdogMinWords = 4,
    this.liveWordsLog,
    this.maxLines = 200,
    this.maxQueuedPackets = 64,
    this.maxInFlightFeeds = 4,
    this.feedChunkBytes = 3200,
    this.maxPacketsPerTurn = 8,
  })  : _engine = engine,
        _now = now ?? DateTime.now,
        _conversationGap = conversationGap ?? (() => const Duration(minutes: 2)),
        _decodeOpus = decodeOpus,
        _requestAllowed = requestAllowed ?? (() async => true),
        _ownResultsMuted = ownResultsMuted ?? (() => ReliabilityExperiments.enabled(muteExperiment)),
        _retimeOwnResults = retimeOwnResults ??
            (() => platform == LivePreviewPlatform.ios && ReliabilityExperiments.enabled(liveWordsExperiment)) {
    // Notes draft from the preview text on this phone; they clear with it.
    notes = LivePreviewNotes(
      engine: notesEngine ?? noLivePreviewNotesEngine,
      telemetry: telemetry,
      platform: platform,
      now: _now,
    )..attach(this);
  }

  final LivePreviewEngine _engine;
  final LivePreviewTelemetry telemetry;
  final LivePreviewPlatform platform;

  late final LivePreviewNotes notes;

  /// OS major version for telemetry; Android resolves it after composition.
  int osMajor;
  final DateTime Function() _now;
  final Duration Function() _conversationGap;
  final List<int> Function(Uint8List opus)? _decodeOpus;
  final Future<bool> Function() _requestAllowed;
  final bool Function() _ownResultsMuted;
  final bool Function() _retimeOwnResults;

  static const liveWordsExperiment = 'vendor_recognizer_on_opened_app';

  /// Test-only reliability experiment: the phone's recogniser runs, and its results are dropped before
  /// display, so the vendor fallback can be seen on a phone whose recogniser works.
  static const muteExperiment = 'phone_recogniser_mute';

  /// Vendor words spanning this long with no result from a recogniser that claims to be streaming
  /// mean it has stalled.
  final Duration watchdogSilence;

  /// A stalled recogniser is restarted at most this often.
  final Duration watchdogMinInterval;
  final int watchdogMinWords;

  /// Local record of what the live-words layer did (counts and times, never text).
  final void Function(String event, Map<String, Object?> fields)? liveWordsLog;
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

  /// What every screen shows. The phone's own recogniser's lines; under reliability experiment
  /// `vendor_recognizer_on_opened_app`, also the vendor stream's words for the stretches the phone's
  /// recogniser returned nothing for ([LiveWordsMerge]). Without vendor lines this is the same list
  /// object as before.
  List<LivePreviewLine> get lines {
    if (_vendorLines.isEmpty) return _linesView;
    return _merged ??= UnmodifiableListView(LiveWordsMerge.merge(_lines, _vendorLines));
  }

  // Vendor stream lines (display only, never stored), kept apart from the phone's own.
  final List<LivePreviewLine> _vendorLines = [];
  List<LivePreviewLine>? _merged;
  List<LivePreviewLine> get vendorLinesForTesting => List.unmodifiable(_vendorLines);

  /// The newest non-empty preview line, for the home capture card's last-line slot.
  String? get latestLine {
    for (final line in lines.reversed) {
      final text = line.text.trim();
      if (text.isNotEmpty) return text;
    }
    return null;
  }

  LivePreviewStart? _start;
  LivePreviewStart? get selected => _start;

  // Separate from socket/engine generation: a silence boundary also clears
  // display state, even when the same engine immediately fills the next line.
  int _sessionGeneration = 0;
  int get sessionGeneration => _sessionGeneration;
  int _totalWordsSeen = 0;
  final Map<String, int> _lineWordHighWater = {};
  int get totalWordsSeen => _totalWordsSeen;

  int _generation = 0;
  Future<void> _serial = Future.value();
  StreamSubscription<LivePreviewResult>? _results;
  DateTime? _lastResultAt;

  // Audio feed (bounded, preview-only).
  final Queue<_PreviewAudio> _queue = Queue();
  bool _drainScheduled = false;
  final BytesBuilder _pending = BytesBuilder(copy: false);
  int _inFlight = 0;
  DateTime? _pendingStartedAt;

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

  // Why the recogniser runs: the server's grant ([admit]), or, under reliability experiment
  // `vendor_recognizer_on_opened_app`, capture being active with the app in front ([setFrontCapture]).
  // It stops when neither holds. Without the experiment only the grant is ever set.
  bool _grantAdmitted = false;
  bool _frontAdmitted = false;

  /// The recogniser runs (also) because capture is active and the app is in front.
  bool get frontAdmitted => _frontAdmitted;

  /// Reliability experiment `vendor_recognizer_on_opened_app`: capture is active and the app is in
  /// front (or no longer). Starts the recogniser without the server's grant, and stops it when the
  /// app leaves the front unless the grant keeps it running. Audio routing is not touched.
  void setFrontCapture(bool active, {required String language}) {
    if (_frontAdmitted == active) return;
    _frontAdmitted = active;
    liveWordsLog?.call('own_recogniser_front', {'active': active, 'granted': _grantAdmitted, 'phase': _phase.name});
    if (active) {
      if (_phase == LivePreviewPhase.inactive) _begin(language);
    } else if (!_grantAdmitted) {
      _end();
    }
  }

  /// The server admitted this socket session. Starts (or keeps) the engine.
  void admit({required String language}) {
    _grantAdmitted = true;
    if (_phase != LivePreviewPhase.inactive) return;
    _begin(language);
  }

  void _begin(String language) {
    final generation = ++_generation;
    _language = language;
    _failedEngines.clear();
    _phase = LivePreviewPhase.starting;
    notifyListeners();
    _startEngine(generation);
  }

  String _language = 'multi';

  /// The language the preview was admitted for (the notes draft in it).
  String get language => _language;

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
      _resetFeedClock();
      telemetry.engineSelected(start, platform: platform, osMajor: osMajor);
      if (start.running) {
        _results = _engine.results.listen((result) {
          if (generation == _generation) _onResult(result);
        }, onError: (Object error) => _onRuntimeFailure(generation, error));
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
      _start = const LivePreviewStart.none(LivePreviewReason.engineError);
      telemetry.engineSelected(_start!, platform: platform, osMajor: osMajor);
      notifyListeners();
      return;
    }
    _startEngine(generation);
  }

  /// Admission ended (socket closed, server revoked, reconnecting). Lines are
  /// kept so a quick re-admission within the same capture continues them.
  void revoke() {
    _grantAdmitted = false;
    // Capture in front keeps the recogniser (reliability experiment vendor_recognizer_on_opened_app).
    if (_frontAdmitted) return;
    _end();
  }

  void _end() {
    if (_phase == LivePreviewPhase.inactive) return;
    _generation++;
    _phase = LivePreviewPhase.inactive;
    _stopEngine();
    notifyListeners();
  }

  /// The capture ended (stop, account change, dispose): the record replaces the
  /// preview through the conversation list's normal refresh, so drop it all.
  void endCapture() {
    final hadState = _phase != LivePreviewPhase.inactive || _lines.isNotEmpty || _vendorLines.isNotEmpty;
    _grantAdmitted = false;
    _frontAdmitted = false;
    _generation++;
    _phase = LivePreviewPhase.inactive;
    _stopEngine();
    _clearLines();
    _lastResultAt = null;
    _lastNotRequested = null;
    _lastOwnWordsAt = null;
    _unansweredSince = null;
    _unansweredWords = 0;
    if (hadState) notifyListeners();
  }

  void _stopEngine() {
    final start = _start;
    _start = null;
    final results = _results;
    _results = null;
    _queue.clear();
    _pending.clear();
    _pendingStartedAt = null;
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
    _enqueue(_PreviewAudio(Uint8List.fromList(packet.sublist(3)), opus: isOpus, receivedAt: _now()));
  }

  /// Phone-mic tap: PCM16 16 kHz mono.
  void onPhonePcm(List<int> pcm) {
    if (!_feeding || pcm.isEmpty) return;
    _enqueue(_PreviewAudio(Uint8List.fromList(pcm), opus: false, receivedAt: _now()));
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
      _pendingStartedAt ??= audio.receivedAt.subtract(Duration(microseconds: pcm.length * 1000000 ~/ 32000));
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
    final startedAt = _pendingStartedAt;
    _pendingStartedAt = null;
    if (chunk.isEmpty) return;
    if (_inFlight >= maxInFlightFeeds) {
      _droppedBytes += chunk.length;
      return;
    }
    _firstAudioAt ??= _now();
    _inFlight++;
    final generation = _generation;
    if (startedAt != null && _retimeOwnResults()) _noteFed(chunk.length, startedAt);
    _engine.feedPcm16(chunk, startedAt: startedAt).then((accepted) {
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
    if (text.isNotEmpty) {
      // The recogniser is alive, whatever is done with its words below.
      ownResultsHeard++;
      _lastOwnWordsAt = now;
      _unansweredSince = null;
      _unansweredWords = 0;
    }
    if (_ownResultsMuted()) return;
    _merged = null;
    if (_feedOrigin != null && _retimeOwnResults()) result = _retimed(result);
    final last = _lastResultAt;
    if (text.isNotEmpty) {
      // A silence as long as the conversation timeout is a conversation
      // boundary: the earlier span becomes its own record, so stop showing it.
      if (last != null && now.difference(last) >= _conversationGap()) _clearLines();
      _lastResultAt = now;
      _noteFirstWord(now);
    }
    final index = _lines.indexWhere((line) => line.id == result.segmentId);
    if (text.isEmpty) {
      if (index >= 0 && !_lines[index].isFinal) _lines.removeAt(index);
      if (result.isFinal) _finalWordCounts.remove(result.segmentId);
    } else {
      final previousWords = _lineWordHighWater[result.segmentId] ?? 0;
      final newWords = _wordCount(text);
      if (newWords > previousWords) {
        _totalWordsSeen += newWords - previousWords;
        _lineWordHighWater[result.segmentId] = newWords;
      }
      final line = LivePreviewLine(
          id: result.segmentId,
          text: text,
          isFinal: result.isFinal,
          startedAt: result.startedAt,
          endedAt: result.endedAt,
          firstSeenAt: index >= 0 ? (_lines[index].firstSeenAt ?? now) : now,
          spans: result.spans);
      if (index >= 0) {
        _lines[index] = line;
      } else {
        _lines.add(line);
        if (_lines.length > maxLines) {
          final evicted = _lines.length - maxLines;
          for (final line in _lines.take(evicted)) {
            _lineWordHighWater.remove(line.id);
          }
          _lines.removeRange(0, evicted);
        }
      }
      if (result.isFinal) _finalWordCounts[result.segmentId] = _wordCount(text);
    }
    notifyListeners();
  }

  void _clearLines() {
    _sessionGeneration++;
    _totalWordsSeen = 0;
    _lineWordHighWater.clear();
    _lines.clear();
    _vendorLines.clear();
    _merged = null;
  }

  // ------------------------------------------ the engine's clock (retiming) --

  // Reliability experiment vendor_recognizer_on_opened_app. The iOS engines time a result on one
  // unbroken audio timeline that starts at the first chunk fed (ios/Runner/LivePreviewPlugin.swift keeps
  // its buffers contiguous on purpose). A pendant that sends nothing while it is quiet makes that
  // timeline fall behind the capture clock by every gap, so a line can be stamped a minute before the
  // audio that produced it. These anchors remember where each stretch of fed audio really sat, and a
  // result is moved back onto the capture clock before anything reads its times: the merge with the
  // vendor's words, the coverage by stored text, and the words-after-an-End rule.
  DateTime? _feedOrigin;
  double _fedMs = 0;
  final List<(double, DateTime)> _feedAnchors = [];
  static const _maxFeedAnchors = 2000;

  void _resetFeedClock() {
    _feedOrigin = null;
    _fedMs = 0;
    _feedAnchors.clear();
  }

  void _noteFed(int bytes, DateTime startedAt) {
    // The engine is told milliseconds; keep the same value it took as its origin.
    final at = DateTime.fromMillisecondsSinceEpoch(startedAt.millisecondsSinceEpoch, isUtc: true);
    _feedOrigin ??= at;
    final last = _feedAnchors.isEmpty ? null : _feedAnchors.last;
    final expected = last?.$2.add(Duration(microseconds: ((_fedMs - last.$1) * 1000).round()));
    // A new anchor where the fed audio leaves its own timeline (a gap in capture), and now and then.
    if (expected == null || at.difference(expected).inMilliseconds.abs() > 200 || _fedMs - last!.$1 >= 5000) {
      _feedAnchors.add((_fedMs, at));
      if (_feedAnchors.length > _maxFeedAnchors) _feedAnchors.removeRange(0, _feedAnchors.length - _maxFeedAnchors);
    }
    _fedMs += bytes / 32;
  }

  /// [at] as the engine reported it (its origin plus audio fed) on the capture clock.
  DateTime _onCaptureClock(DateTime at) {
    final origin = _feedOrigin;
    if (origin == null || _feedAnchors.isEmpty) return at;
    final ms = at.difference(origin).inMicroseconds / 1000;
    if (ms < 0) return at;
    var low = 0, high = _feedAnchors.length - 1;
    while (low < high) {
      final mid = (low + high + 1) >> 1;
      if (_feedAnchors[mid].$1 <= ms) {
        low = mid;
      } else {
        high = mid - 1;
      }
    }
    final (anchorMs, anchorAt) = _feedAnchors[low];
    return anchorAt.add(Duration(microseconds: ((ms - anchorMs) * 1000).round()));
  }

  LivePreviewResult _retimed(LivePreviewResult result) => LivePreviewResult(
        segmentId: result.segmentId,
        text: result.text,
        isFinal: result.isFinal,
        startedAt: result.startedAt == null ? null : _onCaptureClock(result.startedAt!),
        endedAt: result.endedAt == null ? null : _onCaptureClock(result.endedAt!),
        spans: [
          for (final span in result.spans)
            LivePreviewSpan(
                text: span.text, startedAt: _onCaptureClock(span.startedAt), endedAt: _onCaptureClock(span.endedAt)),
        ],
      );

  // ------------------------------------------------- vendor words (display) --

  DateTime? _lastOwnWordsAt;
  DateTime? _unansweredSince;
  int _unansweredWords = 0;
  DateTime? _lastWatchdogRestartAt;

  /// Local reliability measure (reliability experiment `vendor_recognizer_on_opened_app`): words and
  /// milliseconds of speech the vendor stream supplied where the phone's recogniser had returned
  /// nothing when they arrived, and how often a stalled recogniser was restarted. Counts only.
  int ownResultsHeard = 0;
  int vendorWordsSeen = 0;
  int vendorFilledWords = 0;
  int vendorFilledSpeechMs = 0;
  int watchdogRestarts = 0;

  /// New or longer lines from the vendor stream, timed on the phone's capture clock. Display only:
  /// they join [lines] where the phone's recogniser has nothing, and are never stored.
  void onVendorLines(List<LivePreviewLine> updates) {
    if (_phase == LivePreviewPhase.inactive || updates.isEmpty) return;
    final now = _now();
    final last = _lastResultAt;
    // The same conversation boundary as the phone's own lines.
    if (last != null && now.difference(last) >= _conversationGap()) _clearLines();
    _lastResultAt = now;
    final own = LiveWordsMerge.coverage(_lines);
    for (final line in updates) {
      final index = _vendorLines.indexWhere((existing) => existing.id == line.id);
      final previousWords = _lineWordHighWater[line.id] ?? 0;
      final words = line.spans.isEmpty ? _wordCount(line.text) : line.spans.length;
      if (words > previousWords) {
        _totalWordsSeen += words - previousWords;
        vendorWordsSeen += words - previousWords;
        _lineWordHighWater[line.id] = words;
        for (final span in line.spans.skip(previousWords)) {
          if (LiveWordsMerge.covered(own, span.startedAt, span.endedAt)) continue;
          vendorFilledWords++;
          vendorFilledSpeechMs += span.endedAt.difference(span.startedAt).inMilliseconds.clamp(0, 60000);
          _noteUnanswered(span, now);
        }
      }
      if (index >= 0) {
        _vendorLines[index] = line;
      } else {
        _vendorLines.add(line);
        if (_vendorLines.length > maxLines) {
          final evicted = _vendorLines.length - maxLines;
          for (final old in _vendorLines.take(evicted)) {
            _lineWordHighWater.remove(old.id);
          }
          _vendorLines.removeRange(0, evicted);
        }
      }
    }
    _merged = null;
    _checkStalledRecogniser(now);
    notifyListeners();
  }

  /// A vendor word the phone's recogniser has not answered: no line of its own for that audio, and
  /// no result at all since shortly before the word was spoken.
  void _noteUnanswered(LivePreviewSpan span, DateTime now) {
    final ownAt = _lastOwnWordsAt;
    if (ownAt != null && !ownAt.isBefore(span.startedAt.subtract(LiveWordsMerge.tolerance))) return;
    _unansweredSince ??= span.startedAt;
    if (span.startedAt.isBefore(_unansweredSince!)) _unansweredSince = span.startedAt;
    _unansweredWords++;
  }

  /// Vendor words for [watchdogSilence] of speech and none from a recogniser that claims to be
  /// streaming: it has stalled. Restart it, at most once per [watchdogMinInterval].
  void _checkStalledRecogniser(DateTime now) {
    final since = _unansweredSince;
    if (since == null || _unansweredWords < watchdogMinWords) return;
    if (_phase != LivePreviewPhase.streaming || !(_start?.running ?? false)) return;
    if (now.difference(since) < watchdogSilence) return;
    final lastRestart = _lastWatchdogRestartAt;
    if (lastRestart != null && now.difference(lastRestart) < watchdogMinInterval) return;
    _lastWatchdogRestartAt = now;
    watchdogRestarts++;
    liveWordsLog?.call('own_recogniser_restart', {
      'unanswered_words': _unansweredWords,
      'silent_ms': now.difference(since).inMilliseconds,
      'restarts': watchdogRestarts,
    });
    _unansweredSince = null;
    _unansweredWords = 0;
    final generation = ++_generation;
    _stopEngine();
    _phase = LivePreviewPhase.starting;
    _startEngine(generation);
  }

  void _noteFirstWord(DateTime now) {
    final firstAudio = _firstAudioAt;
    final start = _start;
    if (_firstWordSent || firstAudio == null || start == null) return;
    _firstWordSent = true;
    final latency = now.difference(firstAudio).inMilliseconds;
    telemetry.firstWord(start.engine, latencyMs: latency < 0 ? 0 : latency);
  }

  static int _wordCount(String text) => LivePreviewWordBudget.count(text);

  @override
  void dispose() {
    endCapture();
    notes.dispose();
    super.dispose();
  }
}

class _PreviewAudio {
  _PreviewAudio(this.bytes, {required this.opus, required this.receivedAt});

  final Uint8List bytes;
  final bool opus;
  final DateTime receivedAt;
}
