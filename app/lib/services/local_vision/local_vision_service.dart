import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/local_vision/object_announcement_service.dart';
import 'package:omi/services/local_vision/tflite_yoloe_detector.dart';
import 'package:omi/services/local_vision/yoloe_model_assets.dart';
import 'package:omi/utils/logger.dart';

enum AnnouncementMode { allObjects, heldObjectsOnly }

enum LocalVisionDetectorImplementation { fake, yoloe }

extension LocalVisionDetectorImplementationSettings on LocalVisionDetectorImplementation {
  String get preferenceValue => switch (this) {
        LocalVisionDetectorImplementation.fake => 'fake',
        LocalVisionDetectorImplementation.yoloe => 'yoloe',
      };

  String get displayName => switch (this) {
        LocalVisionDetectorImplementation.fake => 'Fake detector',
        LocalVisionDetectorImplementation.yoloe => 'TFLite YOLOE detector',
      };

  static LocalVisionDetectorImplementation fromPreference(String value) {
    return LocalVisionDetectorImplementation.values.firstWhere(
      (implementation) => implementation.preferenceValue == value,
      orElse: () => LocalVisionDetectorImplementation.yoloe,
    );
  }
}

extension AnnouncementModeSettings on AnnouncementMode {
  String get preferenceValue => switch (this) {
        AnnouncementMode.allObjects => 'allObjects',
        AnnouncementMode.heldObjectsOnly => 'heldObjectsOnly',
      };

  String get displayName => switch (this) {
        AnnouncementMode.allObjects => 'All new objects',
        AnnouncementMode.heldObjectsOnly => 'Held objects only',
      };

  static AnnouncementMode fromPreference(String value) {
    return AnnouncementMode.values.firstWhere(
      (mode) => mode.preferenceValue == value,
      orElse: () => AnnouncementMode.allObjects,
    );
  }
}

class DetectionBox {
  const DetectionBox({
    required this.left,
    required this.top,
    required this.width,
    required this.height,
  });

  final double left;
  final double top;
  final double width;
  final double height;

  double get right => left + width;
  double get bottom => top + height;
  double get area {
    final safeWidth = width <= 0 ? 0.0 : width;
    final safeHeight = height <= 0 ? 0.0 : height;
    return safeWidth * safeHeight;
  }

  double intersectionOverUnion(DetectionBox other) {
    final intersectionLeft = left > other.left ? left : other.left;
    final intersectionTop = top > other.top ? top : other.top;
    final intersectionRight = right < other.right ? right : other.right;
    final intersectionBottom = bottom < other.bottom ? bottom : other.bottom;

    final intersectionWidth = intersectionRight - intersectionLeft;
    final intersectionHeight = intersectionBottom - intersectionTop;
    if (intersectionWidth <= 0 || intersectionHeight <= 0) return 0;

    final intersectionArea = intersectionWidth * intersectionHeight;
    final unionArea = area + other.area - intersectionArea;
    if (unionArea <= 0) return 0;

    return intersectionArea / unionArea;
  }

  @override
  String toString() {
    return '(${left.toStringAsFixed(2)}, ${top.toStringAsFixed(2)}, '
        '${width.toStringAsFixed(2)}, ${height.toStringAsFixed(2)})';
  }
}

class Detection {
  const Detection({
    required this.label,
    required this.confidence,
    required this.box,
    required this.sourceFrameId,
    required this.timestamp,
    this.mask,
    this.wouldAnnounce = true,
    this.isHand = false,
    this.maxHandIoU,
    this.heldObjectSelected = false,
    this.heldObjectReason,
  });

  final String label;
  final double confidence;
  final DetectionBox box;
  final String sourceFrameId;
  final DateTime timestamp;
  final Uint8List? mask;
  final bool wouldAnnounce;

  /// True only when the normalized detector label is exactly `hand`.
  final bool isHand;

  /// Maximum bounding-box IoU with any YOLOE `hand` detection in the same frame.
  /// Null outside held-object evaluation, including hand detections themselves.
  final double? maxHandIoU;

  /// Whether this non-hand detection passed strict hand-IoU held-object selection.
  final bool heldObjectSelected;

  /// Metadata-only explanation for debug UI/logs. Never contains image data.
  final String? heldObjectReason;

  String get normalizedLabel => label.trim().toLowerCase();

  Detection copyWith({
    String? label,
    double? confidence,
    DetectionBox? box,
    String? sourceFrameId,
    DateTime? timestamp,
    Uint8List? mask,
    bool? wouldAnnounce,
    bool? isHand,
    double? maxHandIoU,
    bool clearMaxHandIoU = false,
    bool? heldObjectSelected,
    String? heldObjectReason,
    bool clearHeldObjectReason = false,
  }) {
    return Detection(
      label: label ?? this.label,
      confidence: confidence ?? this.confidence,
      box: box ?? this.box,
      sourceFrameId: sourceFrameId ?? this.sourceFrameId,
      timestamp: timestamp ?? this.timestamp,
      mask: mask ?? this.mask,
      wouldAnnounce: wouldAnnounce ?? this.wouldAnnounce,
      isHand: isHand ?? this.isHand,
      maxHandIoU: clearMaxHandIoU ? null : maxHandIoU ?? this.maxHandIoU,
      heldObjectSelected: heldObjectSelected ?? this.heldObjectSelected,
      heldObjectReason: clearHeldObjectReason ? null : heldObjectReason ?? this.heldObjectReason,
    );
  }
}

class LocalVisionLatencyMetrics {
  const LocalVisionLatencyMetrics({
    this.preprocessMs,
    this.inferenceMs,
    this.postprocessMs,
    this.nativeTotalMs,
    this.pipelineTotalMs,
  });

  final double? preprocessMs;
  final double? inferenceMs;
  final double? postprocessMs;
  final double? nativeTotalMs;
  final double? pipelineTotalMs;

  LocalVisionLatencyMetrics copyWith({
    double? preprocessMs,
    double? inferenceMs,
    double? postprocessMs,
    double? nativeTotalMs,
    double? pipelineTotalMs,
  }) {
    return LocalVisionLatencyMetrics(
      preprocessMs: preprocessMs ?? this.preprocessMs,
      inferenceMs: inferenceMs ?? this.inferenceMs,
      postprocessMs: postprocessMs ?? this.postprocessMs,
      nativeTotalMs: nativeTotalMs ?? this.nativeTotalMs,
      pipelineTotalMs: pipelineTotalMs ?? this.pipelineTotalMs,
    );
  }
}

class LocalVisionDetectorResult {
  const LocalVisionDetectorResult({required this.detections, this.latency = const LocalVisionLatencyMetrics()});

  final List<Detection> detections;
  final LocalVisionLatencyMetrics latency;
}

class LocalVisionLatencyAverages {
  const LocalVisionLatencyAverages({
    required this.sampleCount,
    this.preprocessMs,
    this.inferenceMs,
    this.postprocessMs,
    this.nativeTotalMs,
    this.pipelineTotalMs,
  });

  final int sampleCount;
  final double? preprocessMs;
  final double? inferenceMs;
  final double? postprocessMs;
  final double? nativeTotalMs;
  final double? pipelineTotalMs;

  static const empty = LocalVisionLatencyAverages(sampleCount: 0);
}

class HeldObjectDebugState {
  const HeldObjectDebugState({
    required this.mode,
    required this.threshold,
    required this.handCount,
    required this.selectedCount,
    required this.status,
  });

  final AnnouncementMode mode;
  final double threshold;
  final int handCount;
  final int selectedCount;
  final String status;

  static const empty = HeldObjectDebugState(
    mode: AnnouncementMode.allObjects,
    threshold: 0.10,
    handCount: 0,
    selectedCount: 0,
    status: 'Awaiting detections',
  );
}

class LocalVisionFrame {
  const LocalVisionFrame({
    required this.jpegBytes,
    required this.timestamp,
    required this.frameId,
  });

  final Uint8List jpegBytes;
  final DateTime timestamp;
  final String frameId;
}

enum LocalVisionInferenceStatus { idle, queued, running, completed, failed }

abstract class LocalVisionDetector {
  Future<LocalVisionDetectorResult> detect(LocalVisionFrame frame);
}

class FakeLocalVisionDetector implements LocalVisionDetector {
  const FakeLocalVisionDetector();

  @override
  Future<LocalVisionDetectorResult> detect(LocalVisionFrame frame) async {
    final stopwatch = Stopwatch()..start();
    await Future<void>.delayed(const Duration(milliseconds: 120));
    stopwatch.stop();
    return LocalVisionDetectorResult(detections: [
      Detection(
        label: 'cup',
        confidence: 0.91,
        box: const DetectionBox(left: 0.12, top: 0.24, width: 0.22, height: 0.32),
        sourceFrameId: frame.frameId,
        timestamp: frame.timestamp,
      ),
      Detection(
        label: 'phone',
        confidence: 0.86,
        box: const DetectionBox(left: 0.52, top: 0.36, width: 0.24, height: 0.28),
        sourceFrameId: frame.frameId,
        timestamp: frame.timestamp,
      ),
      Detection(
        label: 'keys',
        confidence: 0.78,
        box: const DetectionBox(left: 0.34, top: 0.68, width: 0.2, height: 0.16),
        sourceFrameId: frame.frameId,
        timestamp: frame.timestamp,
      ),
    ], latency: LocalVisionLatencyMetrics(pipelineTotalMs: stopwatch.elapsedMicroseconds / 1000));
  }
}

class _LatencyRollingWindow {
  static const int _maxSamples = 20;

  final List<LocalVisionLatencyMetrics> _samples = [];

  void add(LocalVisionLatencyMetrics metrics) {
    _samples.add(metrics);
    if (_samples.length > _maxSamples) _samples.removeAt(0);
  }

  LocalVisionLatencyAverages get averages {
    if (_samples.isEmpty) return LocalVisionLatencyAverages.empty;
    return LocalVisionLatencyAverages(
      sampleCount: _samples.length,
      preprocessMs: _average((sample) => sample.preprocessMs),
      inferenceMs: _average((sample) => sample.inferenceMs),
      postprocessMs: _average((sample) => sample.postprocessMs),
      nativeTotalMs: _average((sample) => sample.nativeTotalMs),
      pipelineTotalMs: _average((sample) => sample.pipelineTotalMs),
    );
  }

  double? _average(double? Function(LocalVisionLatencyMetrics sample) selector) {
    final values = _samples.map(selector).whereType<double>().toList();
    if (values.isEmpty) return null;
    return values.reduce((a, b) => a + b) / values.length;
  }
}

class AnnouncementCandidate {
  const AnnouncementCandidate({required this.detection, required this.reason});

  final Detection detection;
  final String reason;

  bool get isHighPriorityNewObject =>
      reason == 'entered scene' && detection.confidence >= 0.75 && detection.box.area >= 0.04;
}

double _announcementUsefulnessScore(Detection detection) {
  final confidenceScore = detection.confidence * 0.55;
  final sizeScore = detection.box.area.clamp(0.0, 1.0) * 0.25;
  final centerX = detection.box.left + detection.box.width / 2;
  final centerY = detection.box.top + detection.box.height / 2;
  final distanceFromCenter = ((centerX - 0.5).abs() + (centerY - 0.5).abs()).clamp(0.0, 1.0);
  final centralityScore = (1.0 - distanceFromCenter) * 0.20;
  return confidenceScore + sizeScore + centralityScore;
}

class ObjectPresence {
  ObjectPresence({
    required this.label,
    required this.lastSeenAt,
    required this.confidence,
    required this.box,
    this.lastAnnouncedAt,
  });

  final String label;
  DateTime lastSeenAt;
  double confidence;
  DetectionBox box;
  DateTime? lastAnnouncedAt;
}

class ObjectPresenceTracker {
  final Map<String, ObjectPresence> _presenceByLabel = {};

  List<AnnouncementCandidate> update(
    List<Detection> detections, {
    required DateTime timestamp,
    required AnnouncementMode mode,
  }) {
    final prefs = SharedPreferencesUtil();
    final absenceThreshold = Duration(milliseconds: (prefs.localYoloeObjectAbsenceSeconds * 1000).round());
    final repeatCooldown = Duration(milliseconds: (prefs.localYoloeRepeatCooldownSeconds * 1000).round());
    final cutoff = timestamp.subtract(absenceThreshold);

    _presenceByLabel.removeWhere((label, presence) => presence.lastSeenAt.isBefore(cutoff));

    final filtered = _rankUsefulDetections(_filterForMode(detections, mode));
    final candidates = <AnnouncementCandidate>[];

    for (final detection in filtered.take(prefs.localYoloeMaxObjectsPerAnnouncement)) {
      final labelKey = detection.label.trim().toLowerCase();
      if (labelKey.isEmpty) continue;

      final prior = _presenceByLabel[labelKey];
      final wasAbsent = prior == null || timestamp.difference(prior.lastSeenAt) >= absenceThreshold;
      final canRepeat =
          prior?.lastAnnouncedAt == null || timestamp.difference(prior!.lastAnnouncedAt!) >= repeatCooldown;

      if (prior == null) {
        _presenceByLabel[labelKey] = ObjectPresence(
          label: detection.label,
          lastSeenAt: timestamp,
          confidence: detection.confidence,
          box: detection.box,
        );
      } else {
        prior.lastSeenAt = timestamp;
        prior.confidence = detection.confidence;
        prior.box = detection.box;
      }

      if (wasAbsent || canRepeat) {
        final presence = _presenceByLabel[labelKey]!;
        presence.lastAnnouncedAt = timestamp;
        candidates.add(AnnouncementCandidate(
          detection: detection,
          reason: wasAbsent ? 'entered scene' : 'repeat cooldown elapsed',
        ));
      }
    }

    return candidates;
  }

  List<Detection> _filterForMode(List<Detection> detections, AnnouncementMode mode) {
    if (mode == AnnouncementMode.allObjects) return List<Detection>.from(detections);
    return detections.where((detection) => detection.heldObjectSelected && !detection.isHand).toList();
  }

  List<Detection> _rankUsefulDetections(List<Detection> detections) {
    return List<Detection>.from(detections)
      ..sort((a, b) {
        final scoreComparison = _announcementUsefulnessScore(b).compareTo(_announcementUsefulnessScore(a));
        if (scoreComparison != 0) return scoreComparison;
        return b.confidence.compareTo(a.confidence);
      });
  }

  void clear() => _presenceByLabel.clear();
}

class LocalVisionService extends ChangeNotifier {
  LocalVisionService._({LocalVisionDetector? fakeDetector, LocalVisionDetector? yoloeDetector})
      : _fakeDetector = fakeDetector ?? const FakeLocalVisionDetector(),
        // Do not make this const: the conditionally-exported native detector constructor is non-const.
        // ignore: prefer_const_constructors
        _yoloeDetector = yoloeDetector ?? TfliteYoloeDetector();

  static final LocalVisionService instance = LocalVisionService._();

  final LocalVisionDetector _fakeDetector;
  final LocalVisionDetector _yoloeDetector;
  final ObjectPresenceTracker _presenceTracker = ObjectPresenceTracker();

  LocalVisionInferenceStatus _status = LocalVisionInferenceStatus.idle;
  LocalVisionFrame? _latestFrame;
  LocalVisionFrame? _pendingFrame;
  List<Detection> _detections = [];
  List<AnnouncementCandidate> _announcementCandidates = [];
  final List<DateTime> _receivedFrameTimes = [];
  final List<DateTime> _processedFrameTimes = [];
  DateTime? _lastAcceptedFrameAt;
  int _droppedFrameCount = 0;
  int _receivedFrameCount = 0;
  int _processedFrameCount = 0;
  int _throttledFrameCount = 0;
  Object? _lastError;
  YoloeModelAssetStatus _modelAssetStatus = const YoloeModelAssetStatus.notChecked();
  LocalVisionDetectorImplementation _activeImplementation = LocalVisionDetectorImplementation.yoloe;
  LocalVisionLatencyMetrics _latestLatency = const LocalVisionLatencyMetrics();
  HeldObjectDebugState _heldObjectDebugState = HeldObjectDebugState.empty;
  final _latencyWindow = _LatencyRollingWindow();

  bool _isRunning = false;

  LocalVisionInferenceStatus get status => _status;
  DateTime? get latestFrameTimestamp => _latestFrame?.timestamp;
  String? get latestFrameId => _latestFrame?.frameId;
  Uint8List? get latestFrameJpegBytes => _latestFrame?.jpegBytes;
  List<Detection> get detections => List.unmodifiable(_detections);
  List<AnnouncementCandidate> get announcementCandidates => List.unmodifiable(_announcementCandidates);
  int get detectionCount => _detections.length;
  int get announcementCandidateCount => _announcementCandidates.length;
  int get droppedFrameCount => _droppedFrameCount;
  int get receivedFrameCount => _receivedFrameCount;
  int get processedFrameCount => _processedFrameCount;
  int get throttledFrameCount => _throttledFrameCount;
  bool get hasPendingFrame => _pendingFrame != null;
  double get incomingFrameRateFps => _frameRateFor(_receivedFrameTimes);
  double get inferenceFrameRateFps => _frameRateFor(_processedFrameTimes);
  DateTime? get lastAnnouncementAt => ObjectAnnouncementService.instance.lastAnnouncementAt;
  Object? get lastError => _lastError;
  YoloeModelAssetStatus get modelAssetStatus => _modelAssetStatus;
  LocalVisionDetectorImplementation get activeImplementation => _activeImplementation;
  LocalVisionLatencyMetrics get latestLatency => _latestLatency;
  LocalVisionLatencyAverages get averageLatency => _latencyWindow.averages;
  HeldObjectDebugState get heldObjectDebugState => _heldObjectDebugState;

  Future<void> initialize() async {
    _modelAssetStatus = await YoloeModelAssets.validate();
    if (_modelAssetStatus.isValid) {
      Logger.debug(
        'Local YOLOE model assets validated: labels=${_modelAssetStatus.labelCount} '
        'input=${_modelAssetStatus.inputSize} dir=${_modelAssetStatus.modelDirectory}',
      );
    } else {
      _lastError = _modelAssetStatus.error;
      _status = LocalVisionInferenceStatus.failed;
      _activeImplementation = _selectDetectorImplementation();
      Logger.error(
        'Local YOLOE model unavailable: ${_modelAssetStatus.error}. '
        'Detector fallback=${_activeImplementation.preferenceValue}',
      );
    }
    notifyListeners();
  }

  Future<void> submitFrame(Uint8List jpegBytes, {DateTime? timestamp}) async {
    final capturedAt = timestamp ?? DateTime.now();
    _receivedFrameCount++;
    _trackFrameTime(_receivedFrameTimes, capturedAt);

    if (!_canProcessFrames) {
      _lastError = _modelAssetStatus.error ?? 'Local YOLOE model assets have not been validated';
      _status = LocalVisionInferenceStatus.failed;
      notifyListeners();
      return;
    }

    final frame = LocalVisionFrame(
      jpegBytes: jpegBytes,
      timestamp: capturedAt,
      frameId: 'local_vision_${capturedAt.microsecondsSinceEpoch}',
    );

    _latestFrame = frame;
    _lastError = null;

    if (_isRunning) {
      if (_pendingFrame != null) {
        _droppedFrameCount++;
      }
      // Keep only the newest pending frame. Older pending frame bytes become
      // unreachable here, so the VM can reclaim them instead of queueing stale images.
      // This app-side scheduler processes every received frame when inference is fast enough;
      // actual Omi Glass image cadence can still be limited by firmware/photo-controller timing.
      _pendingFrame = frame;
      _status = LocalVisionInferenceStatus.queued;
      notifyListeners();
      return;
    }

    if (_shouldThrottleFrame(capturedAt)) {
      _throttledFrameCount++;
      notifyListeners();
      return;
    }

    _lastAcceptedFrameAt = capturedAt;

    await _runFrame(frame);
  }

  Future<void> _runFrame(LocalVisionFrame frame) async {
    _isRunning = true;
    _status = LocalVisionInferenceStatus.running;
    notifyListeners();

    try {
      final implementation = _selectDetectorImplementation();
      final detector = _detectorFor(implementation);
      _activeImplementation = implementation;
      Logger.debug(
        'Local YOLOE processing rotated JPEG bytes frame=${frame.frameId} '
        'bytes=${frame.jpegBytes.length} detector=${implementation.preferenceValue}',
      );
      final pipelineStopwatch = Stopwatch()..start();
      final detectorResult = await detector.detect(frame);
      pipelineStopwatch.stop();
      final latency = detectorResult.latency.copyWith(pipelineTotalMs: pipelineStopwatch.elapsedMicroseconds / 1000);
      _latestLatency = latency;
      _latencyWindow.add(latency);
      _processedFrameCount++;
      _trackFrameTime(_processedFrameTimes, DateTime.now());
      final prefs = SharedPreferencesUtil();
      final confidenceThreshold = prefs.localYoloeConfidenceThreshold;
      final maxObjectsPerFrame = prefs.localYoloeMaxObjectsPerFrame;
      final rawResults = detectorResult.detections
          .where((detection) => detection.confidence >= confidenceThreshold)
          .toList()
        ..sort((a, b) => b.confidence.compareTo(a.confidence));
      final thresholdedResults = rawResults.take(maxObjectsPerFrame).toList();
      final mode = AnnouncementModeSettings.fromPreference(SharedPreferencesUtil().localYoloeAnnouncementMode);
      final handIouThreshold = prefs.localYoloeHandObjectIouThreshold;
      final annotatedResults = _annotateHeldObjectSelection(thresholdedResults, mode, handIouThreshold);
      final handCount = annotatedResults.where((detection) => detection.isHand).length;
      final heldSelectedCount = annotatedResults.where((detection) => detection.heldObjectSelected).length;
      _heldObjectDebugState = HeldObjectDebugState(
        mode: mode,
        threshold: handIouThreshold,
        handCount: handCount,
        selectedCount: heldSelectedCount,
        status: _heldObjectStatusFor(mode, handCount, heldSelectedCount, annotatedResults.length),
      );
      final candidates = _presenceTracker.update(annotatedResults, timestamp: frame.timestamp, mode: mode);
      final candidatesToSpeak = _announcementCandidatesAllowedBySpeechGuardrails(candidates);
      final candidateLabels = candidatesToSpeak.map((candidate) => candidate.detection.label.toLowerCase()).toSet();
      final results = annotatedResults
          .map(
            (detection) => detection.copyWith(
              wouldAnnounce: candidateLabels.contains(detection.label.toLowerCase()),
            ),
          )
          .toList();
      _detections = results;
      _announcementCandidates = candidatesToSpeak;
      _status = LocalVisionInferenceStatus.completed;
      Logger.debug(
        'Local YOLOE detections frame=${frame.frameId} '
        'detector=${implementation.preferenceValue} count=${results.length} announce=${candidatesToSpeak.length} '
        'mode=${mode.preferenceValue} threshold=${confidenceThreshold.toStringAsFixed(2)} '
        'handCount=$handCount handIouThreshold=${handIouThreshold.toStringAsFixed(2)} '
        'heldSelected=$heldSelectedCount '
        'latencyMs=${latency.pipelineTotalMs?.toStringAsFixed(1) ?? 'unknown'} '
        'preprocessMs=${latency.preprocessMs?.toStringAsFixed(1) ?? 'unknown'} '
        'inferenceMs=${latency.inferenceMs?.toStringAsFixed(1) ?? 'unknown'} '
        'postprocessMs=${latency.postprocessMs?.toStringAsFixed(1) ?? 'unknown'} '
        'detectorTotalMs=${latency.nativeTotalMs?.toStringAsFixed(1) ?? 'unknown'} '
        'labels=${results.map((detection) => detection.label).join(',')}',
      );
      _logHeldObjectSelectionDecisions(
        frameId: frame.frameId,
        mode: mode,
        handCount: handCount,
        handIouThreshold: handIouThreshold,
        detections: results,
      );
      if (candidatesToSpeak.isNotEmpty) {
        await ObjectAnnouncementService.instance.speakObjects(
          candidatesToSpeak.map((candidate) => candidate.detection.label).toList(),
          bypassQuietPeriod: _hasHighPriorityNewObject(candidatesToSpeak),
        );
      }
    } catch (e, stackTrace) {
      _lastError = e;
      _status = LocalVisionInferenceStatus.failed;
      Logger.error('Local YOLOE detection failed: $e\n$stackTrace');
    } finally {
      _isRunning = false;
      notifyListeners();
    }

    final nextFrame = _pendingFrame;
    if (nextFrame != null) {
      _pendingFrame = null;
      if (_shouldThrottleFrame(nextFrame.timestamp)) {
        _throttledFrameCount++;
        notifyListeners();
      } else {
        _lastAcceptedFrameAt = nextFrame.timestamp;
        await _runFrame(nextFrame);
      }
    }
  }

  List<AnnouncementCandidate> _announcementCandidatesAllowedBySpeechGuardrails(List<AnnouncementCandidate> candidates) {
    if (candidates.isEmpty) return candidates;

    final prefs = SharedPreferencesUtil();
    final maxObjects = prefs.localYoloeMaxObjectsPerAnnouncement.clamp(1, 5).toInt();
    final rankedCandidates = List<AnnouncementCandidate>.from(candidates)
      ..sort((a, b) {
        final highPriorityComparison = (b.isHighPriorityNewObject ? 1 : 0).compareTo(a.isHighPriorityNewObject ? 1 : 0);
        if (highPriorityComparison != 0) return highPriorityComparison;
        final usefulnessComparison =
            _announcementUsefulnessScore(b.detection).compareTo(_announcementUsefulnessScore(a.detection));
        if (usefulnessComparison != 0) return usefulnessComparison;
        return b.detection.confidence.compareTo(a.detection.confidence);
      });

    final lastAnnouncementAt = ObjectAnnouncementService.instance.lastAnnouncementAt;
    if (lastAnnouncementAt != null && !_hasHighPriorityNewObject(rankedCandidates)) {
      final quietPeriod = Duration(milliseconds: (prefs.localYoloeMinSecondsBetweenAnnouncements * 1000).round());
      final quietUntil = lastAnnouncementAt.add(quietPeriod);
      if (DateTime.now().isBefore(quietUntil)) {
        Logger.debug(
          'Local YOLOE announcement suppressed by quiet period: '
          'candidateCount=${rankedCandidates.length} quietUntil=${quietUntil.toIso8601String()}',
        );
        return const [];
      }
    }

    return rankedCandidates.take(maxObjects).toList();
  }

  bool _hasHighPriorityNewObject(List<AnnouncementCandidate> candidates) {
    return candidates.any((candidate) => candidate.isHighPriorityNewObject);
  }

  List<Detection> _annotateHeldObjectSelection(
    List<Detection> detections,
    AnnouncementMode mode,
    double handIouThreshold,
  ) {
    final handDetections = detections.where((detection) => detection.normalizedLabel == 'hand').toList();
    final handBoxes = handDetections.map((detection) => detection.box).toList();

    return detections.map((detection) {
      final isHand = detection.normalizedLabel == 'hand';
      if (mode != AnnouncementMode.heldObjectsOnly) {
        return detection.copyWith(
          isHand: isHand,
          maxHandIoU: isHand ? null : _maxIoUWithHandBoxes(detection.box, handBoxes),
          heldObjectSelected: false,
          clearHeldObjectReason: true,
        );
      }

      if (isHand) {
        return detection.copyWith(
          isHand: true,
          clearMaxHandIoU: true,
          heldObjectSelected: false,
          heldObjectReason: 'hand anchor only; never announced',
        );
      }

      if (handBoxes.isEmpty) {
        return detection.copyWith(
          isHand: false,
          maxHandIoU: 0,
          heldObjectSelected: false,
          heldObjectReason: 'rejected: no YOLOE hand detection',
        );
      }

      final maxHandIoU = _maxIoUWithHandBoxes(detection.box, handBoxes);
      final selected = maxHandIoU > handIouThreshold;
      return detection.copyWith(
        isHand: false,
        maxHandIoU: maxHandIoU,
        heldObjectSelected: selected,
        heldObjectReason: selected
            ? 'selected: hand IoU ${maxHandIoU.toStringAsFixed(2)} > ${handIouThreshold.toStringAsFixed(2)}'
            : 'rejected: hand IoU ${maxHandIoU.toStringAsFixed(2)} <= ${handIouThreshold.toStringAsFixed(2)}',
      );
    }).toList();
  }

  String _heldObjectStatusFor(AnnouncementMode mode, int handCount, int selectedCount, int detectionCount) {
    if (mode != AnnouncementMode.heldObjectsOnly) return 'All-object mode; hand IoU is diagnostic only';
    if (detectionCount == 0) return 'No detections above confidence threshold';
    if (handCount == 0) return 'No hand detected; held-object mode intentionally selects nothing';
    if (selectedCount == 0) return 'Hand detected; no object exceeded the hand-IoU threshold';
    return 'Hand detected; $selectedCount held object${selectedCount == 1 ? '' : 's'} selected';
  }

  void _logHeldObjectSelectionDecisions({
    required String frameId,
    required AnnouncementMode mode,
    required int handCount,
    required double handIouThreshold,
    required List<Detection> detections,
  }) {
    if (mode != AnnouncementMode.heldObjectsOnly) return;

    if (detections.isEmpty) {
      Logger.debug(
        'Local YOLOE held-object decision frame=$frameId handCount=$handCount '
        'threshold=${handIouThreshold.toStringAsFixed(2)} status=no_detections',
      );
      return;
    }

    for (final detection in detections) {
      Logger.debug(
        'Local YOLOE held-object decision frame=$frameId handCount=$handCount '
        'threshold=${handIouThreshold.toStringAsFixed(2)} label=${detection.normalizedLabel} '
        'confidence=${detection.confidence.toStringAsFixed(2)} '
        'isHand=${detection.isHand} maxHandIoU=${(detection.maxHandIoU ?? 0).toStringAsFixed(2)} '
        'selected=${detection.heldObjectSelected} reason=${detection.heldObjectReason ?? 'n/a'}',
      );
    }
  }

  double _maxIoUWithHandBoxes(DetectionBox box, List<DetectionBox> handBoxes) {
    var maxIoU = 0.0;
    for (final handBox in handBoxes) {
      final iou = box.intersectionOverUnion(handBox);
      if (iou > maxIoU) maxIoU = iou;
    }
    return maxIoU;
  }

  bool _shouldThrottleFrame(DateTime capturedAt) {
    final interval = _effectiveMinFrameInterval;
    if (interval == Duration.zero) return false;

    final lastAccepted = _lastAcceptedFrameAt;
    if (lastAccepted == null) return false;

    return capturedAt.difference(lastAccepted) < interval;
  }

  Duration get _effectiveMinFrameInterval {
    final prefs = SharedPreferencesUtil();
    Duration minInterval = Duration.zero;

    final maxFps = prefs.localYoloeMaxFps;
    if (maxFps > 0) {
      minInterval = Duration(microseconds: (Duration.microsecondsPerSecond / maxFps).round());
    }

    if (prefs.localYoloeAdaptiveThrottlingEnabled) {
      final averagePipelineMs = _latencyWindow.averages.pipelineTotalMs;
      if (averagePipelineMs != null && averagePipelineMs > 0) {
        final adaptiveInterval = Duration(microseconds: (averagePipelineMs * 1250).round());
        if (adaptiveInterval > minInterval) {
          minInterval = adaptiveInterval;
        }
      }
    }

    return minInterval;
  }

  void _trackFrameTime(List<DateTime> samples, DateTime timestamp) {
    samples.add(timestamp);
    final cutoff = timestamp.subtract(const Duration(seconds: 10));
    samples.removeWhere((sample) => sample.isBefore(cutoff));
  }

  double _frameRateFor(List<DateTime> samples) {
    if (samples.length < 2) return 0;
    final elapsedMs = samples.last.difference(samples.first).inMilliseconds;
    if (elapsedMs <= 0) return 0;
    return (samples.length - 1) * 1000 / elapsedMs;
  }

  bool get _canProcessFrames {
    final implementation = _selectDetectorImplementation();
    if (implementation == LocalVisionDetectorImplementation.fake) return true;
    return _modelAssetStatus.isValid;
  }

  LocalVisionDetectorImplementation _selectDetectorImplementation() {
    final requested = LocalVisionDetectorImplementationSettings.fromPreference(
      SharedPreferencesUtil().localYoloeDetectorImplementation,
    );
    if (requested == LocalVisionDetectorImplementation.fake) {
      return LocalVisionDetectorImplementation.fake;
    }
    if (_modelAssetStatus.isValid) {
      return LocalVisionDetectorImplementation.yoloe;
    }
    return LocalVisionDetectorImplementation.fake;
  }

  LocalVisionDetector _detectorFor(LocalVisionDetectorImplementation implementation) {
    return switch (implementation) {
      LocalVisionDetectorImplementation.fake => _fakeDetector,
      LocalVisionDetectorImplementation.yoloe => _yoloeDetector,
    };
  }
}
