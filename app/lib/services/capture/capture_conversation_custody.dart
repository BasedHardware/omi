part of 'capture_controller.dart';

/// An admitted close owns its audio cut and evidence, even when later conversations finish first.
/// A capture-session refresh may not revoke this durable work; account retirement may.
class _ConversationClose {
  _ConversationClose({
    required this.phone,
    required this.walGeneration,
    required this.epoch,
    required this.captureToken,
    required this.windowRevision,
    required this.sessionStartSeconds,
    required this.recordingId,
    required this.segmentArrivals,
    required this.needsRepair,
    required this.customStt,
    required this.snapshot,
  });

  final dynamic phone;
  final int? walGeneration;
  final CaptureSessionToken? captureToken;
  Future<_ConversationClose?>? evidenceAuthority;
  final int epoch, windowRevision, sessionStartSeconds;
  final String? recordingId;
  final Map<String, int> segmentArrivals;
  final bool needsRepair, customStt;
  final Future<ConversationWalSnapshot?> snapshot;
  final Completer<String?> decision = Completer<String?>();
  late final Future<void> stamped;
  Timer? fallback;

  void bind(String? id) {
    if (!decision.isCompleted) decision.complete(id);
  }
}

extension _CaptureConversationCustody on CaptureController {
  bool _closeStoreIsCurrent(_ConversationClose close) =>
      close.epoch == _conversationCustodyEpoch &&
      (close.walGeneration == null ||
          (close.phone is LocalWalSync && close.phone.sessionGeneration == close.walGeneration));

  void _rememberConversationClose(String id) {
    _seenConversationCloses.add(id);
    if (_seenConversationCloses.length > 128) _seenConversationCloses.remove(_seenConversationCloses.first);
  }

  /// Admission is synchronous: do not defer the audio cut behind a previous stamp or HTTP result.
  _ConversationClose _admitConversationClose({bool processNow = false}) {
    final phone = _wal.getSyncs().phone;
    final start = _sessionStartSeconds;
    final recordingId = activeRecordingId;
    final snapshot = phone is LocalWalSyncImpl
        ? phone.finalizeAndSnapshotSession(sessionStartSeconds: start, recordingSessionId: recordingId)
        : (() async {
            // Narrow staged test seams have no ledger; production always takes the opaque cut.
            await phone.finalizeCurrentSession();
            return null as ConversationWalSnapshot?;
          })();
    final close = _ConversationClose(
      phone: phone,
      walGeneration: phone is LocalWalSync ? phone.sessionGeneration : null,
      epoch: _conversationCustodyEpoch,
      captureToken: _sessionOwner?.token,
      windowRevision: _conversationWindowRevision,
      sessionStartSeconds: start,
      recordingId: recordingId,
      segmentArrivals: Map.unmodifiable(_segmentArrivals),
      needsRepair: _sessionTransportInterrupted,
      customStt: _socket?.customSttMode ?? _lastPublishedSocketCustomStt,
      snapshot: snapshot,
    );
    _admittedConversationCloses.add(close);
    final predecessor = _pendingFinalizeAndStamp;
    close.stamped = (() async {
      try {
        // Observe snapshot errors immediately, even while an earlier request is unresolved.
        final cut = await snapshot;
        if (predecessor != null) await predecessor;
        final id = await close.decision.future;
        if (id == null || start <= 0 || !_closeStoreIsCurrent(close)) return;
        if (phone is LocalWalSyncImpl) {
          if (cut != null) await phone.stampConversationSnapshot(cut, id);
        } else {
          await phone.stampConversationId(start, id);
        }
      } catch (error, stack) {
        // A failed write leaves recoverable audio and must not poison later close slots.
        Logger.debug('Conversation WAL close failed: ${error.runtimeType}');
        await _reportDetachedCaptureError(
            processNow ? 'capture_process_now' : 'capture_conversation_close', error, stack);
      } finally {
        _admittedConversationCloses.remove(close);
      }
    })();
    _pendingFinalizeAndStamp = close.stamped;
    return close;
  }

  void _resetLiveConversationWindow() {
    final continuing = _sessionStartSeconds > 0 &&
        recordingState != RecordingState.stop &&
        recordingState != RecordingState.error &&
        recordingState != RecordingState.initialising;
    _sessionTransportInterrupted = false;
    // Reset and rearm before notifying; selectors must never observe a transient null window.
    _resetStateVariables(rearmLive: continuing);
    if (!continuing) _clearSessionLocation();
  }

  void _onConversationProcessingStarted(String id) {
    if (_seenConversationCloses.contains(id)) return;
    _rememberConversationClose(id);
    final processes = _pendingProcessCloses.where(_closeStoreIsCurrent).toList();
    final sameWindow = processes
        .where((process) =>
            process.windowRevision == _conversationWindowRevision && process.recordingId == activeRecordingId)
        .toList();
    // A server close during Process Now's drain adopts that exact cut. Its revision guard then
    // returns without issuing a second process request or abandoning the reserved audio.
    // An older unresolved request makes even the currently draining window ambiguous.
    final adopted = sameWindow.isNotEmpty && processes.length == 1 ? sameWindow.first : null;
    final close = adopted ?? _admitConversationClose();
    if (adopted == null && processes.isNotEmpty) {
      // Several Process Now requests can be awaiting HTTP at once. Only their exact response IDs
      // can disambiguate an intervening server close; the newest request alone is not authority.
      close.evidenceAuthority = Future.wait(processes.map((process) => process.decision.future)).then((ids) {
        final matched = ids.indexOf(id);
        if (matched >= 0) {
          close.bind(null); // Intervening audio stays unlinked and recoverable.
          return processes[matched];
        }
        if (ids.contains(null)) {
          close.bind(null);
          return null;
        }
        close.bind(id);
        return close;
      });
    } else {
      close.bind(id);
    }
    _pendingConversationCloses[id] = close;
    _resetLiveConversationWindow();
    close.fallback = _scheduling.once(const Duration(seconds: 30), () {
      if (!identical(_pendingConversationCloses[id], close)) return;
      _pendingConversationCloses.remove(id);
      unawaited(_confirmMissingConversation(close, id));
    });
  }

  Future<void> _confirmClosedConversation(_ConversationClose admitted, ServerConversation saved) async {
    final close = admitted.evidenceAuthority == null ? admitted : await admitted.evidenceAuthority;
    if (close == null) return;
    await _confirmSessionTranscript(close.sessionStartSeconds, saved, close.segmentArrivals,
        close: close, needsRepair: close.needsRepair, allowTranscriptCoverageFallback: close.customStt);
  }

  Future<void> _confirmMissingConversation(_ConversationClose admitted, String id) async {
    final close = admitted.evidenceAuthority == null ? admitted : await admitted.evidenceAuthority;
    if (close == null) return;
    await _confirmSessionWalsRetained(close.sessionStartSeconds, id,
        close: close, failClosedReason: 'missing_conversation_event');
  }

  void _retireConversationClosures({required bool accountChanged}) {
    for (final close in _pendingConversationCloses.values) {
      close.fallback?.cancel();
    }
    _pendingConversationCloses.clear();
    if (accountChanged) {
      _conversationCustodyEpoch++;
      for (final close in _admittedConversationCloses.toList()) {
        close.bind(null);
      }
      _admittedConversationCloses.clear();
      _seenConversationCloses.clear();
      _pendingProcessCloses.clear();
      // Retired-account I/O must not block the next account's chain.
      _pendingFinalizeAndStamp = null;
    }
  }

  /// Moves the safety copies [conversation]'s saved transcript covers into synced retention, and
  /// uploads the uncovered rest so the server can transcribe what it lost. When coverage cannot be
  /// judged — an interrupted session, an empty or unusable transcript, or no anchor — confirmation
  /// passes no spans and fails closed: every eligible stamped copy is kept for repair.
  Future<void> _confirmSessionTranscript(
    int sessionStartSeconds,
    ServerConversation conversation,
    Map<String, int> segmentArrivals, {
    required _ConversationClose close,
    bool needsRepair = false,
    bool allowTranscriptCoverageFallback = false,
  }) {
    List<(int, int)>? spans;
    int? origin;
    String? failClosedReason;
    final saved = conversation.transcriptSegments;
    if (needsRepair) {
      failClosedReason = 'needs_repair';
    } else if (saved.isEmpty) {
      failClosedReason = 'empty_transcript';
    } else {
      final valid = [
        for (final segment in saved)
          if (segment.start.isFinite && segment.end.isFinite && segment.end > segment.start) segment,
      ];
      if (valid.isEmpty) {
        failClosedReason = 'no_spans';
      } else {
        // Live segment times are seconds from the conversation's start on the server's clock, while
        // the copies carry the phone's. Anchor that start to the phone through the moments the live
        // segments arrived; without any, use the server's start, or this session's when the row has
        // none.
        final startedAt = conversation.startedAt;
        final anchor =
            transcriptStartOnDevice([for (final segment in valid) (segment.id, segment.end)], segmentArrivals) ??
                (startedAt != null
                    ? startedAt.millisecondsSinceEpoch ~/ 1000
                    : (sessionStartSeconds > 0 ? sessionStartSeconds : null));
        if (anchor == null || anchor <= 0) {
          failClosedReason = 'anchor_unavailable';
        } else {
          origin = anchor;
          spans = [for (final segment in valid) (anchor + segment.start.floor(), anchor + segment.end.ceil())];
        }
      }
    }
    return _confirmSessionWalsRetained(sessionStartSeconds, conversation.id,
        close: close,
        transcriptSpans: spans,
        conversationStartSeconds: origin,
        failClosedReason: failClosedReason,
        allowTranscriptCoverageFallback: allowTranscriptCoverageFallback);
  }

  Future<void> _confirmSessionWalsRetained(
    int sessionStartSeconds,
    String conversationId, {
    required _ConversationClose close,
    List<(int, int)>? transcriptSpans,
    int? conversationStartSeconds,
    String? failClosedReason,
    bool allowTranscriptCoverageFallback = false,
  }) async {
    final phone = close.phone;
    await close.stamped;
    bool stillCurrent() => !_captureControllerDisposed && _closeStoreIsCurrent(close);
    if (!stillCurrent()) return;
    var kept = 0;
    if (phone is LocalWalSyncImpl) {
      try {
        final outcome = await phone.confirmSessionTranscription(sessionStartSeconds, conversationId,
            transcriptSpans: transcriptSpans,
            conversationStartSeconds: conversationStartSeconds,
            failClosedReason: failClosedReason,
            allowTranscriptCoverageFallback: allowTranscriptCoverageFallback);
        kept = outcome.kept;
      } catch (e) {
        Logger.debug('_confirmSessionWalsRetained error: $e');
        kept = 1;
      }
    }
    if (!stillCurrent()) return;
    if (_captureSessionIsCurrent(close.captureToken) && (kept > 0 || phone is! LocalWalSyncImpl)) {
      _autoSyncSessionWals(trigger: WakeTrigger.dataStalled);
    }
  }
}
