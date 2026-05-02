import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';

import 'package:omi/backend/http/api/ambient_capture.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/ambient_capture/ambient_capture_health.dart';
import 'package:omi/services/ambient_capture/ambient_capture_models.dart';
import 'package:omi/services/ambient_capture/ambient_capture_service.dart';
import 'package:omi/services/ambient_capture/fallback_segment_queue.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/logger.dart';

class AmbientCaptureProvider extends ChangeNotifier {
  final AmbientCaptureService service;
  final FallbackSegmentQueue fallbackQueue;

  CaptureProvider? _captureProvider;
  StreamSubscription? _audioSub;
  StreamSubscription? _healthSub;
  StreamSubscription? _telemetrySub;
  Timer? _fallbackDrainTimer;
  Timer? _spoolDrainTimer;
  int _fallbackBackoffSeconds = 5;
  int _spoolBackoffSeconds = 10;

  AmbientCaptureHealth _health = AmbientCaptureHealth(
    state: AmbientCaptureHealthState.policyDisabled,
    timestamp: DateTime.now(),
  );
  bool _running = false;
  bool _privateMode = false;
  String _policyStatus = 'No controller selected';
  DateTime? _lastPolicySync;
  int _pendingFallbackCount = 0;
  int _pendingSpoolCount = 0;
  int _spoolBytes = 0;

  AmbientCaptureProvider({AmbientCaptureService? service, FallbackSegmentQueue? fallbackQueue})
      : service = service ?? AmbientCaptureService(),
        fallbackQueue = fallbackQueue ?? FallbackSegmentQueue();

  static void applyFullCoverageDefaults() {
    final prefs = SharedPreferencesUtil();
    prefs.advancedAmbientCaptureEnabled = true;
    prefs.ambientCaptureMode = 'aggressive';
    prefs.ambientCaptureSensitivity = 'high';
    prefs.ambientCaptureTextFallbackEnabled = true;
    prefs.ambientCaptureLocalSttFallbackEnabled = true;
    prefs.ambientCaptureCaptionFallbackEnabled = true;
    prefs.ambientCaptureAccessibilityModeEnabled = true;
    prefs.ambientCaptureRawAudioUploadEnabled = true;
    prefs.ambientCaptureCommunicationMode = 'detect_and_caption_fallback';
    prefs.ambientCaptureRawAudioRetention = 'until_synced';
  }

  bool get isSupported => service.isSupported;
  bool get running => _running;
  bool get privateMode => _privateMode;
  AmbientCaptureHealth get health => _health;
  String get policyStatus => _policyStatus;
  DateTime? get lastPolicySync => _lastPolicySync;
  int get pendingFallbackCount => _pendingFallbackCount;
  int get pendingSpoolCount => _pendingSpoolCount;
  int get spoolBytes => _spoolBytes;

  void setCaptureProvider(CaptureProvider provider) {
    _captureProvider = provider;
  }

  Future<void> initialize() async {
    if (!isSupported) return;
    _healthSub ??= service.healthStream.listen((health) {
      _health = health;
      notifyListeners();
    });
    _telemetrySub ??= service.telemetryStream.listen(_handleTelemetry);
    await _syncNativePolicyConfig();
    await refreshSpoolStats();
    _fallbackDrainTimer ??= Timer.periodic(const Duration(seconds: 30), (_) => drainFallbackQueue());
    _spoolDrainTimer ??= Timer.periodic(const Duration(minutes: 2), (_) => drainNativeSpool());
  }

  Future<bool> start() async {
    if (!SharedPreferencesUtil().advancedAmbientCaptureEnabled || !isSupported) return false;
    await initialize();
    await _captureProvider?.prepareAdvancedAmbientCapture();
    await _syncNativePolicyConfig();
    _audioSub ??= service.audioStream.listen((bytes) {
      _captureProvider?.ingestAdvancedAmbientAudio(bytes);
    });
    await service.start();
    await Future.delayed(const Duration(milliseconds: 900));
    final status = await service.getStatus();
    _running = status['running'] == true;
    _privateMode = status['privateMode'] == true;
    if (_running) {
      await _updateNativeState();
    } else {
      await _audioSub?.cancel();
      _audioSub = null;
      await _captureProvider?.stopAdvancedAmbientCapture();
      _health = await service.getHealthState();
    }
    notifyListeners();
    return _running;
  }

  Future<void> pause() async {
    await service.pause();
    _running = true;
    _health = AmbientCaptureHealth(state: AmbientCaptureHealthState.pausedByUser, timestamp: DateTime.now());
    notifyListeners();
  }

  Future<void> resume() async {
    if (!SharedPreferencesUtil().advancedAmbientCaptureEnabled) return;
    await service.resume();
    _privateMode = false;
    notifyListeners();
  }

  Future<void> stop() async {
    await service.stop();
    await _audioSub?.cancel();
    _audioSub = null;
    await _captureProvider?.stopAdvancedAmbientCapture();
    _running = false;
    _privateMode = false;
    notifyListeners();
  }

  Future<void> enablePrivateMode() async {
    await service.privateMode(enabled: true);
    await _captureProvider?.enterAdvancedAmbientPrivateMode();
    _privateMode = true;
    notifyListeners();
  }

  Future<void> _updateNativeState() async {
    try {
      final phoneSync = ServiceManager.instance().wal.getSyncs().phone;
      await service.setFlutterState(
        socketConnected: _captureProvider?.transcriptServiceReady == true,
        networkAvailable: ConnectivityService().isConnected,
        walQueueDepth: phoneSync.getInFlightSeconds(),
      );
    } catch (e) {
      Logger.debug('AmbientCaptureProvider state update failed: $e');
    }
  }

  Future<void> _syncNativePolicyConfig() async {
    final prefs = SharedPreferencesUtil();
    await service.setPolicyConfig(
      activePluginId: prefs.ambientCaptureActiveControllerAppId,
      publicKey: prefs.ambientCaptureControllerPublicKey,
      keyId: prefs.ambientCaptureControllerKeyId,
      deviceToken: prefs.ambientCaptureControllerDeviceToken,
      policyUrl: prefs.ambientCapturePolicyUrl,
      userId: prefs.uid,
      deviceId: prefs.ambientCaptureRegisteredDeviceId,
    );
  }

  Future<void> _handleTelemetry(AmbientCaptureTelemetryEvent event) async {
    if (event.type == 'fallback_segment_queued' && SharedPreferencesUtil().ambientCaptureTextFallbackEnabled) {
      final text = event.metadata['text']?.toString();
      if (text != null && text.trim().isNotEmpty) {
        final now = DateTime.now();
        await fallbackQueue.enqueue(
          AmbientFallbackSegment(
            text: text,
            source: AmbientFallbackSource.accessibilityCaption,
            start: now,
            end: now,
            healthState: _health.state,
            foregroundAppPackage: event.metadata['foregroundPackage']?.toString(),
            rawAudioAvailable: false,
          ),
        );
        await _refreshPendingFallbackCount();
        await drainFallbackQueue();
      }
    }
  }

  Future<void> drainFallbackQueue() async {
    if (!SharedPreferencesUtil().ambientCaptureTextFallbackEnabled) return;
    final pending = await fallbackQueue.loadPending();
    _pendingFallbackCount = pending.length;
    notifyListeners();
    if (pending.isEmpty || !ConnectivityService().isConnected) return;
    try {
      final conversationId = await uploadAmbientFallbackSegments(
        deviceId: 'android-ambient-phone-mic',
        segments: pending,
      );
      if (conversationId == null) throw Exception('fallback upload failed');
      await fallbackQueue.markUploaded(pending);
      await fallbackQueue.clearUploaded();
      _fallbackBackoffSeconds = 5;
      _pendingFallbackCount = (await fallbackQueue.loadPending()).length;
      notifyListeners();
    } catch (e) {
      Logger.debug('Ambient fallback drain failed: $e');
      final delay = _fallbackBackoffSeconds;
      _fallbackBackoffSeconds = (_fallbackBackoffSeconds * 2).clamp(5, 300).toInt();
      Future.delayed(Duration(seconds: delay), drainFallbackQueue);
    }
  }

  Future<void> drainNativeSpool() async {
    if (!ConnectivityService().isConnected || !SharedPreferencesUtil().ambientCaptureRawAudioUploadEnabled) return;
    final files = (await service.listSpoolFiles()).where((file) => file.isPending && file.bytes > 0).toList();
    _pendingSpoolCount = files.length;
    notifyListeners();
    if (files.isEmpty) return;
    try {
      final diskFiles = files.map((file) => File(file.filePath)).where((file) => file.existsSync()).toList();
      if (diskFiles.isEmpty) return;
      await syncLocalFilesV2(diskFiles);
      await service.markSpoolFiles(files.map((file) => file.filePath).toList(), 'synced');
      _spoolBackoffSeconds = 10;
      await refreshSpoolStats();
    } catch (e) {
      Logger.debug('Ambient native spool drain failed: $e');
      final delay = _spoolBackoffSeconds;
      _spoolBackoffSeconds = (_spoolBackoffSeconds * 2).clamp(10, 600).toInt();
      Future.delayed(Duration(seconds: delay), drainNativeSpool);
    }
  }

  Future<void> refreshSpoolStats() async {
    final stats = await service.getSpoolStats();
    _pendingSpoolCount = (stats['pendingCount'] as num?)?.toInt() ?? 0;
    _spoolBytes = (stats['totalBytes'] as num?)?.toInt() ?? 0;
    await _refreshPendingFallbackCount();
    notifyListeners();
  }

  Future<void> deleteNativeSpool({String? status}) async {
    await service.deleteSpoolFiles(status: status);
    await refreshSpoolStats();
  }

  Future<void> _refreshPendingFallbackCount() async {
    _pendingFallbackCount = (await fallbackQueue.loadPending()).length;
  }

  void markPolicyStatus(String status) {
    _policyStatus = status;
    _lastPolicySync = DateTime.now();
    notifyListeners();
  }

  @override
  void dispose() {
    _audioSub?.cancel();
    _healthSub?.cancel();
    _telemetrySub?.cancel();
    _fallbackDrainTimer?.cancel();
    _spoolDrainTimer?.cancel();
    super.dispose();
  }
}
