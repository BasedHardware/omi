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
    LocalSegmentStore? localSegmentStore,
  }) : localSegmentStore = localSegmentStore ?? LocalSegmentStore.disabled() {
    addListener(_persistLiveSegments);
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
        .map((segment) =>
            '${segment.id}:${segment.speaker}:${segment.speakerId}:${segment.isUser}:${segment.personId ?? ''}:${segment.text}')
        .join('\n');
    if (fingerprint == _lastPersistedFingerprint) return;
    _lastPersistedFingerprint = fingerprint;
    final pending = List.of(segments);
    _liveSegmentWrite =
        _liveSegmentWrite.then((_) => localSegmentStore.replaceSession(sessionId, pending)).catchError((Object e) {
      Logger.debug('Error persisting live segments: $e');
    });
    unawaited(_liveSegmentWrite);
  }

  @override
  void dispose() {
    removeListener(_persistLiveSegments);
    super.dispose();
  }
}
