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
    super.processInProgressOutcome,
    super.deviceConnectionLoader,
    super.pendantReconnect,
    super.pendantReconnectBlocked,
    super.omiCallState,
    super.captureWedgeMonitor,
    super.calendarGapMonitor,
    super.mobileStandardBatch,
    LocalSegmentStore? localSegmentStore,
  }) : localSegmentStore = localSegmentStore ?? LocalSegmentStore.disabled() {
    addListener(_persistLiveSegments);
    lifetime.own(() => removeListener(_persistLiveSegments));
  }

  final LocalSegmentStore localSegmentStore;

  /// Whether a write is queued but not yet started, and for which owner generation.
  bool _liveSegmentWriteQueued = false;
  (int, String)? _queuedLiveSegmentWriteToken;
  _LiveSegmentsKey? _lastSeenSegmentsKey;
  Future<void> _liveSegmentWrite = Future<void>.value();

  Future<void> get pendingLiveSegmentWrite => _liveSegmentWrite;

  void _persistLiveSegments() {
    if (!localSegmentStore.enabled) return;
    final sessionId = activeCaptureSessionId ?? activeRecordingId;
    if (sessionId == null) {
      // Do not keep the last capture's transcript alive through the key.
      _lastSeenSegmentsKey = null;
      return;
    }
    // This listener runs on every capture notify (state, metrics, sockets),
    // most of which leave the transcript untouched. Skip unless the list, its
    // length or the content version moved, so no notify walks the transcript.
    // In-place segment edits must bump segmentsPhotosVersion; the live
    // transcript UI relies on that already.
    final ownerToken = sessionOwner?.token;
    final key = _LiveSegmentsKey(
      sessionId: sessionId,
      ownerGeneration: ownerToken?.generation,
      ownerIdentity: ownerToken?.identity,
      segments: segments,
      length: segments.length,
      version: segmentsPhotosVersion,
    );
    if (key == _lastSeenSegmentsKey) return;
    _lastSeenSegmentsKey = key;
    final owner = sessionOwner;
    final token = owner?.token;
    final tokenKey = token == null ? null : (token.generation, token.identity);
    // Coalesce: a write already queued for this owner generation takes the
    // latest transcript when it runs, so a burst of segment events costs one
    // snapshot per completed write instead of one O(transcript) copy each.
    if (_liveSegmentWriteQueued && _queuedLiveSegmentWriteToken == tokenKey) return;
    _liveSegmentWriteQueued = true;
    _queuedLiveSegmentWriteToken = tokenKey;
    _liveSegmentWrite = _liveSegmentWrite.then((_) async {
      if (_queuedLiveSegmentWriteToken == tokenKey) _liveSegmentWriteQueued = false;
      if (owner != null && token != null && !owner.isCurrent(token)) return;
      final currentSession = activeCaptureSessionId ?? activeRecordingId;
      if (currentSession == null) return;
      await localSegmentStore.replaceSession(currentSession, List.of(segments));
    }).catchError((Object e) {
      // Let the next notify retry.
      _lastSeenSegmentsKey = null;
      Logger.debug('Error persisting live segments: $e');
    });
    unawaited(_liveSegmentWrite);
  }
}

class _LiveSegmentsKey {
  const _LiveSegmentsKey({
    required this.sessionId,
    required this.ownerGeneration,
    required this.ownerIdentity,
    required this.segments,
    required this.length,
    required this.version,
  });

  final String sessionId;
  final int? ownerGeneration;
  final String? ownerIdentity;
  final List<Object?> segments;
  final int length;
  final int version;

  @override
  bool operator ==(Object other) =>
      other is _LiveSegmentsKey &&
      other.sessionId == sessionId &&
      other.ownerGeneration == ownerGeneration &&
      other.ownerIdentity == ownerIdentity &&
      identical(other.segments, segments) &&
      other.length == length &&
      other.version == version;

  @override
  int get hashCode =>
      Object.hash(sessionId, ownerGeneration, ownerIdentity, identityHashCode(segments), length, version);
}
