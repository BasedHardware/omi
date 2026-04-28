import 'dart:async';

import 'package:flutter/foundation.dart';

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

  AmbientCaptureHealth _health = AmbientCaptureHealth(
    state: AmbientCaptureHealthState.policyDisabled,
    timestamp: DateTime.now(),
  );
  bool _running = false;
  bool _privateMode = false;
  String _policyStatus = 'No controller selected';
  DateTime? _lastPolicySync;

  AmbientCaptureProvider({AmbientCaptureService? service, FallbackSegmentQueue? fallbackQueue})
      : service = service ?? AmbientCaptureService(),
        fallbackQueue = fallbackQueue ?? FallbackSegmentQueue();

  bool get isSupported => service.isSupported;
  bool get running => _running;
  bool get privateMode => _privateMode;
  AmbientCaptureHealth get health => _health;
  String get policyStatus => _policyStatus;
  DateTime? get lastPolicySync => _lastPolicySync;

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
  }

  Future<void> start() async {
    if (!SharedPreferencesUtil().advancedAmbientCaptureEnabled || !isSupported) return;
    await initialize();
    await _captureProvider?.prepareAdvancedAmbientCapture();
    _audioSub ??= service.audioStream.listen((bytes) {
      _captureProvider?.ingestAdvancedAmbientAudio(bytes);
    });
    _running = await service.start();
    _privateMode = false;
    await _updateNativeState();
    notifyListeners();
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
      }
    }
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
    super.dispose();
  }
}
