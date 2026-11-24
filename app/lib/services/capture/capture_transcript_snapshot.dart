part of 'capture_controller.dart';

/// Server transcript reads and ordered projection, separate from preview text.
extension _CaptureTranscriptSnapshot on CaptureController {
  Future<void> _processNewSegmentReceived(List<TranscriptSegment> newSegments) async {
    if (newSegments.isEmpty) return;
    final arrivedAt = _nowSeconds;
    for (final segment in newSegments) {
      _segmentArrivals[segment.id] = arrivedAt;
    }
    _recordingTelemetry.observeTranscript();
    final deviceId = _recordingDevice?.id;
    if (deviceId != null) _wedgeMonitor.onTranscriptObserved(deviceId);

    if (segments.isEmpty && !_isLoadingInProgressConversation) {
      _isLoadingInProgressConversation = true;
      // Product: recording is the tap; location is metadata. Refresh at the
      // first transcript without relying on the long-lived foreground-task
      // isolate. Fail-open: do not delay segment processing.
      unawaited(_conversationLocationCapture.captureAndUpload());
      try {
        await _loadInProgressConversation();
      } finally {
        _isLoadingInProgressConversation = false;
      }
    }

    retainManualLiveLabels(segments, newSegments, _manualSpeakerDefaults);
    final remainSegments = TranscriptSegment.updateSegments(segments, newSegments);
    segments.addAll(remainSegments);
    segments.sort((a, b) => a.start.compareTo(b.start));

    for (final segment in newSegments) {
      // A persisted manual positive label for an excluded speaker means the
      // server's manual receipt may have a newer authoritative assignment
      // (another surface replaced the exclusion; the receipt projects
      // exclusions as unlabeled, never as manual). The socket path carries no
      // assignment generation, so provenance alone cannot order a stale
      // pre-exclusion label against the exclusion: keep the exclusion and let
      // an authoritative snapshot decide. applyInProgressConversation retires
      // the local exclusion when the persisted snapshot really does carry the
      // newer manual positive.
      if (_excludedSpeakers.contains(segment.speakerId) &&
          segment.speakerLabelSource == 'manual' &&
          (segment.isUser || (segment.personId?.isNotEmpty ?? false))) {
        _scheduleExclusionReconcileRefresh();
      }
    }
    // Excluded ("Not a person") speakers stay unlabeled as live segments for
    // them arrive: a live label must not resurrect an acknowledged exclusion.
    if (_excludedSpeakers.isNotEmpty) {
      for (final segment in segments) {
        if (_excludedSpeakers.contains(segment.speakerId)) {
          segment.isUser = false;
          segment.personId = null;
          segment.speakerLabelSource = null;
        }
      }
    }

    // Refresh people cache if we see unknown personIds (backend-created persons)
    // Check all newSegments, not just remainSegments, to catch updates to existing segments
    if (_peopleRefreshFuture == null && _hasMissingPerson(newSegments)) {
      _peopleRefreshFuture = externalActions.refreshPeople().whenComplete(() {
        _peopleRefreshFuture = null;
      }).catchError((Object error, StackTrace stack) {
        Logger.debug('People cache refresh failed: ${error.runtimeType}');
        return _reportDetachedCaptureError('capture_people_refresh_segments', error, stack);
      });
    }

    _segmentsPhotosVersion++; // Bump version so Selector rebuilds
    hasTranscripts = true;
    _publishCaptureChange();
  }
}
