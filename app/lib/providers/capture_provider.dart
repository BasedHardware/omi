import 'dart:async';

import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/utils/logger.dart';

class CaptureProvider extends CaptureController {
  CaptureProvider({
    super.externalActions,
    super.conversationLocationCapture,
    super.inProgressConversationLoader,
    super.audioCodecLoader,
    super.microphonePermissionRequester,
    super.phoneMicBatchRecorder,
    super.recordingTelemetry,
    super.speakerHaptic,
    super.walService,
    super.phoneMicRecorder,
    super.phoneMicBatchSupported,
    super.connectivity,
    super.authBoundary,
    super.now,
    super.scheduling,
    super.preferences,
    super.bleListeners,
    super.openSocket,
    super.sessionOwner,
    super.processInProgressConversation,
    super.deviceConnectionLoader,
    super.omiCallState,
    super.captureWedgeMonitor,
    LocalSegmentStore? localSegmentStore,
  }) : localSegmentStore = localSegmentStore ?? LocalSegmentStore.disabled() {
    addListener(_persistLiveSegments);
    lifetime.own(() => removeListener(_persistLiveSegments));
  }

  final LocalSegmentStore localSegmentStore;
  String? _lastPersistedFingerprint;
  Future<void> _liveSegmentWrite = Future<void>.value();

  Future<void> get pendingLiveSegmentWrite => _liveSegmentWrite;

  void _persistLiveSegments() {
    if (!localSegmentStore.enabled) return;
    final sessionId = activeCaptureSessionId ?? activeRecordingId;
    if (sessionId == null) return;
    final fingerprint = segments
        .map(
          (segment) =>
              '${segment.id}:${segment.speaker}:${segment.speakerId}:${segment.isUser}:${segment.personId ?? ''}:${segment.text}',
        )
        .join('\n');
    if (fingerprint == _lastPersistedFingerprint) return;
    final pending = List.of(segments);
    final owner = sessionOwner;
    final token = owner?.token;
    _liveSegmentWrite = _liveSegmentWrite.then((_) async {
      if (owner != null && token != null && !owner.isCurrent(token)) return;
      await localSegmentStore.replaceSession(sessionId, pending);
      if (owner != null && token != null && !owner.isCurrent(token)) return;
      _lastPersistedFingerprint = fingerprint;
    }).catchError((Object e) {
      Logger.debug('Error persisting live segments: $e');
    });
    unawaited(_liveSegmentWrite);
  }
}
