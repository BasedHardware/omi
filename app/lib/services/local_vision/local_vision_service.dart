import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/local_vision/android_yoloe_detector.dart';
import 'package:omi/services/local_vision/object_announcement_service.dart';
import 'package:omi/services/local_vision/yoloe_model_assets.dart';
import 'package:omi/utils/logger.dart';

enum AnnouncementMode { allObjects, heldObjectsOnly }

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
  });

  final String label;
  final double confidence;
  final DetectionBox box;
  final String sourceFrameId;
  final DateTime timestamp;
  final Uint8List? mask;
  final bool wouldAnnounce;
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
  Future<List<Detection>> detect(LocalVisionFrame frame);
}

class FakeLocalVisionDetector implements LocalVisionDetector {
  const FakeLocalVisionDetector();

  @override
  Future<List<Detection>> detect(LocalVisionFrame frame) async {
    await Future<void>.delayed(const Duration(milliseconds: 120));
    return [
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
    ];
  }
}

class AnnouncementCandidate {
  const AnnouncementCandidate({required this.detection, required this.reason});

  final Detection detection;
  final String reason;
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

    final filtered = _filterForMode(detections, mode)..sort((a, b) => b.confidence.compareTo(a.confidence));
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
    return detections.where(_isLikelyHeldObject).toList();
  }

  bool _isLikelyHeldObject(Detection detection) {
    final centerX = detection.box.left + detection.box.width / 2;
    final centerY = detection.box.top + detection.box.height / 2;
    return centerX >= 0.25 && centerX <= 0.75 && centerY >= 0.55;
  }

  void clear() => _presenceByLabel.clear();
}

class LocalVisionService extends ChangeNotifier {
  LocalVisionService._({LocalVisionDetector? detector})
      : _detector = detector ?? (Platform.isAndroid ? AndroidYoloeDetector() : const FakeLocalVisionDetector());

  static final LocalVisionService instance = LocalVisionService._();

  final LocalVisionDetector _detector;
  final ObjectPresenceTracker _presenceTracker = ObjectPresenceTracker();

  LocalVisionInferenceStatus _status = LocalVisionInferenceStatus.idle;
  LocalVisionFrame? _latestFrame;
  LocalVisionFrame? _pendingFrame;
  List<Detection> _detections = [];
  List<AnnouncementCandidate> _announcementCandidates = [];
  int _droppedFrameCount = 0;
  Object? _lastError;
  YoloeModelAssetStatus _modelAssetStatus = const YoloeModelAssetStatus.notChecked();

  bool _isRunning = false;

  LocalVisionInferenceStatus get status => _status;
  DateTime? get latestFrameTimestamp => _latestFrame?.timestamp;
  String? get latestFrameId => _latestFrame?.frameId;
  List<Detection> get detections => List.unmodifiable(_detections);
  List<AnnouncementCandidate> get announcementCandidates => List.unmodifiable(_announcementCandidates);
  int get detectionCount => _detections.length;
  int get announcementCandidateCount => _announcementCandidates.length;
  int get droppedFrameCount => _droppedFrameCount;
  Object? get lastError => _lastError;
  YoloeModelAssetStatus get modelAssetStatus => _modelAssetStatus;

  Future<void> initialize() async {
    _modelAssetStatus = await YoloeModelAssets.validate();
    if (_modelAssetStatus.isValid) {
      Logger.debug(
        'Local YOLOE model assets validated: labels=${_modelAssetStatus.labelCount} '
        'input=${_modelAssetStatus.inputSize} dir=${_modelAssetStatus.modelDirectory}',
      );
    } else {
      SharedPreferencesUtil().localYoloeEnabled = false;
      _lastError = _modelAssetStatus.error;
      _status = LocalVisionInferenceStatus.failed;
      Logger.error('Local YOLOE disabled: ${_modelAssetStatus.error}');
    }
    notifyListeners();
  }

  Future<void> submitFrame(Uint8List jpegBytes, {DateTime? timestamp}) async {
    if (!_modelAssetStatus.isValid) {
      _lastError = _modelAssetStatus.error ?? 'Local YOLOE model assets have not been validated';
      _status = LocalVisionInferenceStatus.failed;
      notifyListeners();
      return;
    }

    final capturedAt = timestamp ?? DateTime.now();
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
      _pendingFrame = frame;
      _status = LocalVisionInferenceStatus.queued;
      notifyListeners();
      return;
    }

    await _runFrame(frame);
  }

  Future<void> _runFrame(LocalVisionFrame frame) async {
    _isRunning = true;
    _status = LocalVisionInferenceStatus.running;
    notifyListeners();

    try {
      final rawResults = await _detector.detect(frame);
      final mode = AnnouncementModeSettings.fromPreference(SharedPreferencesUtil().localYoloeAnnouncementMode);
      final candidates = _presenceTracker.update(rawResults, timestamp: frame.timestamp, mode: mode);
      final candidateLabels = candidates.map((candidate) => candidate.detection.label.toLowerCase()).toSet();
      final results = rawResults
          .map(
            (detection) => Detection(
              label: detection.label,
              confidence: detection.confidence,
              box: detection.box,
              sourceFrameId: detection.sourceFrameId,
              timestamp: detection.timestamp,
              mask: detection.mask,
              wouldAnnounce: candidateLabels.contains(detection.label.toLowerCase()),
            ),
          )
          .toList();
      _detections = results;
      _announcementCandidates = candidates;
      _status = LocalVisionInferenceStatus.completed;
      Logger.debug(
        'Local YOLOE detections frame=${frame.frameId} '
        'count=${results.length} announce=${candidates.length} mode=${mode.preferenceValue} '
        'labels=${results.map((detection) => detection.label).join(',')}',
      );
      if (candidates.isNotEmpty) {
        await ObjectAnnouncementService.instance.speakObjects(
          candidates.map((candidate) => candidate.detection.label).toList(),
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
      await _runFrame(nextFrame);
    }
  }
}
