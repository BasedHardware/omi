part of 'local_wal_sync.dart';

extension _WalJobCompletion on LocalWalSyncImpl {
  Future<SyncLocalFilesResponse> _reconcileUploadedWals() async {
    final generation = _sessionGeneration;
    final resp = SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []);

    final completed = <SyncLocalFilesResponse>[];
    bool changed = false;
    bool heldChanged = false;
    final nowSecs = _now().millisecondsSinceEpoch ~/ 1000;
    // A restored uploaded row with no job handle cannot ever be polled.
    // Retained audio re-enters the normal deduplicated upload path; missing
    // audio remains visible as unavailable. Neither is a successful sync.
    // Iterate a snapshot: a recording admitted during a file check must not
    // break the pass, and each row is re-read after the check before it moves.
    final orphans = _wals.where((w) => _stillUploadedUnder(w, null)).toList();
    for (final w in orphans) {
      final exists = await _localFileExists(w);
      if (!_isCurrent(generation)) return resp;
      if (!_stillUploadedUnder(w, null)) continue;
      changed = true;
      heldChanged |= w.holdForUser;
      if (exists) {
        w.status = WalStatus.miss;
        w.jobId = null;
        w.lastRetryAt = nowSecs;
      } else {
        w.markCorrupted();
      }
      DebugLogManager.logEvent('reconcile_revert', {
        'walId': w.id,
        'outcome': 'missing_job_id',
        'fileExists': exists,
        'newStatus': w.status.name,
      });
    }

    final byJob = <String, List<Wal>>{};
    for (final w in _wals) {
      if (w.status == WalStatus.uploaded && w.jobId != null && w.jobId!.isNotEmpty) {
        byJob.putIfAbsent(w.jobId!, () => []).add(w);
      }
    }
    // Serial requests let a 429 stop this pass before another request escapes.
    const maxConcurrent = 1;
    // Fresh uploads and old handles alternate; a dead backlog cannot starve them.
    final uploadedAt = {for (final e in byJob.entries) e.key: e.value.map((w) => w.uploadedAt).reduce(max)};
    final entries =
        _jobPoller.ordered(byJob.keys, uploadedAtSeconds: uploadedAt).map((id) => MapEntry(id, byJob[id]!)).toList();

    for (var i = 0; i < entries.length; i += maxConcurrent) {
      final slice = entries.sublist(i, min(i + maxConcurrent, entries.length));
      if (SyncRateLimiter.instance.isLimited || !_isCurrent(generation)) break;
      final fetched = await Future.wait(slice.map((e) async => (e.value, await _jobStatusFetcher(e.key))));
      if (!_isCurrent(generation)) return resp;

      for (final (members, fetch) in fetched) {
        final jobId = members.first.jobId;
        final memberWalIds = members.map((w) => w.id).toList();
        switch (fetch.outcome) {
          case SyncJobFetchOutcome.throttled:
            if (!SyncRateLimiter.instance.isLimited) {
              final limit = fetch.rateLimit;
              SyncRateLimiter.instance.markLimited(
                retryAfterSeconds: limit?.retryAfterSeconds,
                reason: limit?.kind.cooldownReason ?? RateLimitReason.edgeThrottle,
              );
            }
            break; // 429 rate limit cooldown installed; stop reconcile pass below (#21279).
          case SyncJobFetchOutcome.transient:
            // Network/5xx — leave as `uploaded`, retry on the next pass.
            DebugLogManager.logEvent('reconcile_poll', {
              'jobId': jobId,
              'memberWalIds': memberWalIds,
              'outcome': 'transient',
            });
            break;
          case SyncJobFetchOutcome.notFound:
            // Job expired or unknown. Recover from the retained local file.
            for (final w in members) {
              final hadJob = w.jobId;
              final fileExists = await _localFileExists(w);
              if (!_isCurrent(generation)) return resp;
              if (!_stillUploadedUnder(w, jobId)) continue;
              changed = true;
              heldChanged |= w.holdForUser;
              w.jobId = null;
              if (fileExists) {
                w.status = WalStatus.miss; // re-upload next sync (dedup-safe)
                // Expiry is not an audio failure. Recovery is already paced by
                // two missing reads separated by five minutes.
                w.lastRetryAt = nowSecs;
              } else {
                w.markCorrupted(); // nothing left to recover
              }
              DebugLogManager.logEvent('reconcile_revert', {
                'walId': w.id,
                'jobId': hadJob,
                'outcome': 'not_found',
                'fileExists': fileExists,
                'newStatus': w.status.name,
                'retryCount': w.retryCount,
              });
            }
            break;
          case SyncJobFetchOutcome.ok:
            final s = fetch.status!;
            final terminalPolicy = syncJobTerminalPolicy(status: s.status, isTerminal: s.isTerminal);
            if (terminalPolicy == SyncJobTerminalPolicy.wait) {
              DebugLogManager.logEvent('reconcile_poll', {
                'jobId': jobId,
                'memberWalIds': memberWalIds,
                'outcome': 'non_terminal',
                'serverStatus': s.status,
                'processedSegments': s.processedSegments,
                'totalSegments': s.totalSegments,
              });
              break; // still queued/processing — check later
            }
            if (s.result != null) {
              resp.newConversationIds.addAll(
                s.result!.newConversationIds.where((id) => !resp.newConversationIds.contains(id)),
              );
              resp.updatedConversationIds.addAll(
                s.result!.updatedConversationIds.where(
                  (id) => !resp.updatedConversationIds.contains(id) && !resp.newConversationIds.contains(id),
                ),
              );
            }
            if (terminalPolicy == SyncJobTerminalPolicy.acknowledge) {
              if (s.result != null) completed.add(s.result!);
              DebugLogManager.logEvent('reconcile_poll', {
                'jobId': jobId,
                'memberWalIds': memberWalIds,
                'outcome': 'completed',
                'newConversations': s.result?.newConversationIds.length ?? 0,
                'updatedConversations': s.result?.updatedConversationIds.length ?? 0,
              });
              try {
                ClientTelemetry.instance.observeUploadDurableCompleted(jobId: jobId, confirmedAt: _now());
              } catch (_) {
                // Completion telemetry must not change WAL acknowledgement.
              }
              for (final w in members) {
                if (!_stillUploadedUnder(w, jobId)) continue;
                if ((s.result?.newConversationIds.length ?? 0) == 0 &&
                    (s.result?.updatedConversationIds.length ?? 0) == 0) {
                  DebugLogManager.logEvent('reconcile_completed_empty', {
                    'jobId': w.jobId,
                    'walId': w.id,
                    'walKey': _durableKey(w),
                    'newConversations': s.result?.newConversationIds.length ?? 0,
                    'updatedConversations': s.result?.updatedConversationIds.length ?? 0,
                    'processedSegments': s.processedSegments,
                    'totalSegments': s.totalSegments,
                    'retryCount': w.retryCount,
                    'capacityLimited': false,
                    'retryCountBumped': false,
                  });
                }
                changed = true;
                heldChanged |= w.holdForUser;
                w.status = WalStatus.synced;
                w.holdForUser = false;
                w.jobId = null;
                if (w.syncedAt == 0) w.syncedAt = _now().millisecondsSinceEpoch ~/ 1000;
                if (_isCurrent(generation)) listener.onWalSynced(w);
              }
            } else {
              // status='failed' with totalSegments==0 can only come from the
              // backend stale guard (mark_job_completed only sets 'failed'
              // when total>0). String hint is a fallback if the structural
              // signal ever becomes ambiguous.
              final capacityLimited = syncJobIsBackendBusy(s) || isPacedBackfillReasonCode(s.reasonCode);
              if (capacityLimited) {
                SyncRateLimiter.instance.markLimited(
                  retryAfterSeconds: s.retryAfter ?? 600,
                  reason: RateLimitReason.backendBusy,
                );
              }
              // A verdict the audio itself caused cannot change on the next pass,
              // and it cannot change for a manual retry either — the bytes are the
              // same. Spending the auto budget only made the row read "Failed — tap
              // Retry" forever: every tap re-uploaded, re-earned the same verdict,
              // and re-spent the budget, with the needs-attention banner never
              // clearing. Retire it to a terminal state instead, the way an
              // out-of-window rejection already does. The file stays on disk.
              final permanentInput = !capacityLimited && syncJobFailureIsPermanent(s);
              for (final w in members) {
                if (!_stillUploadedUnder(w, jobId)) continue;
                changed = true;
                heldChanged |= w.holdForUser;
                final hadJob = w.jobId;
                if (permanentInput) {
                  w.markUnsupportedAudio();
                  w.lastRetryAt = nowSecs;
                } else {
                  w.status = WalStatus.miss;
                  w.jobId = null;
                  if (!capacityLimited) {
                    w.retryCount += 1;
                    w.lastRetryAt = nowSecs;
                  }
                }
                DebugLogManager.logEvent('reconcile_revert', {
                  'walId': w.id,
                  'jobId': hadJob,
                  'outcome': s.status,
                  'serverError': s.error,
                  'reasonCode': s.reasonCode,
                  'failedSegments': s.failedSegments,
                  'totalSegments': s.totalSegments,
                  'retryCount': w.retryCount,
                  'capacityLimited': capacityLimited,
                  'permanentInput': permanentInput,
                  'retryCountBumped': !capacityLimited,
                });
              }
            }
            break;
        }
        if (SyncRateLimiter.instance.isLimited) break;
      }
      if (SyncRateLimiter.instance.isLimited) break;
    }

    if (changed) {
      await _saveWalsToFile(generation);
      _notifyUpdated(generation);
    }
    if (heldChanged && _isCurrent(generation)) heldRevision.value++;
    _publishConversationCompletions(completed, generation);
    return resp;
  }
}
