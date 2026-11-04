import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';

/// Upload/job boundaries only. Production batching, state transitions, index
/// persistence, notifications and reconcile admission still run unchanged.
class HeavyUploadFixture {
  HeavyUploadFixture() {
    gate = SyncUploadGate(
      limiter: SyncRateLimiter.instance,
      fairUseStatusLoader: () async => {'stage': 'none'},
      uploader: (files,
          {onUploadProgress,
          conversationId,
          captureEvidence,
          recordingSessionId,
          audioStartSeconds,
          audioEndSeconds,
          claimLiveCapture = false,
          geolocation}) async {
        if (!accepting) {
          // Existing lifecycle window retains the real delayed loopback 429.
          return uploadLocalFilesV2(files,
              onUploadProgress: onUploadProgress,
              conversationId: conversationId,
              captureEvidence: captureEvidence,
              recordingSessionId: recordingSessionId,
              audioStartSeconds: audioStartSeconds,
              audioEndSeconds: audioEndSeconds,
              claimLiveCapture: claimLiveCapture,
              geolocation: geolocation);
        }
        // Read real synthetic framed bytes; no decoder or network is involved.
        for (final file in files) {
          acceptedBytes += await file.openRead().fold<int>(0, (sum, bytes) => sum + bytes.length);
          acceptedFiles++;
        }
        final id = 'perf-upload-job-${_jobs.length}';
        _jobs.add(id);
        return UploadFilesResult.queued(id, pollAfterMs: 0);
      },
    );
  }

  late final SyncUploadGate gate;
  bool accepting = false;
  final _jobs = <String>{};
  int acceptedFiles = 0;
  int acceptedBytes = 0;
  int completedJobs = 0;
  int get acceptedJobs => _jobs.length;

  Future<SyncJobFetch> fetchJob(String id) async {
    if (!_jobs.contains(id)) throw StateError('Unknown synthetic upload job');
    completedJobs++;
    return SyncJobFetch(
      SyncJobFetchOutcome.ok,
      SyncJobStatusResponse(
        jobId: id,
        status: 'completed',
        result: SyncLocalFilesResponse(newConversationIds: [], updatedConversationIds: []),
      ),
    );
  }
}
