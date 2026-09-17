import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/wal.dart';

void main() {
  group('syncJobTerminalPolicy', () {
    test('acknowledges only a truthful completed terminal job', () {
      expect(
        syncJobTerminalPolicy(status: 'completed', isTerminal: true),
        SyncJobTerminalPolicy.acknowledge,
      );
    });

    test('retains retry material for partial and full failures', () {
      for (final status in ['partial_failure', 'failed']) {
        expect(
          syncJobTerminalPolicy(status: status, isTerminal: true),
          SyncJobTerminalPolicy.retry,
          reason: '$status must never acknowledge the local WAL',
        );
      }
    });

    test('waits for nonterminal jobs regardless of their status text', () {
      expect(
        syncJobTerminalPolicy(status: 'processing', isTerminal: false),
        SyncJobTerminalPolicy.wait,
      );
      expect(
        syncJobTerminalPolicy(status: 'completed', isTerminal: false),
        SyncJobTerminalPolicy.wait,
      );
    });
  });

  group('synchronous sync upload policy', () {
    test('rejects a legacy HTTP 200 with failed segments so the WAL remains retryable', () {
      final response = SyncLocalFilesResponse(
        newConversationIds: const ['already-processed-conversation'],
        updatedConversationIds: const [],
        failedSegments: 1,
        totalSegments: 2,
      );

      expect(
        () => requireCompleteSyncUpload(response),
        throwsA(
          isA<SyncUploadIncompleteException>().having(
            (error) => error.failedSegments,
            'failedSegments',
            1,
          ),
        ),
      );
    });
  });

  group('syncJobIsBackendBusy', () {
    SyncJobStatusResponse status({String? reasonCode, String? error}) {
      return SyncJobStatusResponse(
        jobId: 'synthetic-job',
        status: 'failed',
        totalSegments: 0,
        processedSegments: 0,
        successfulSegments: 0,
        failedSegments: 0,
        reasonCode: reasonCode,
        error: error,
      );
    }

    test('recognizes the legacy stale-worker shape', () {
      expect(syncJobIsBackendBusy(status()), isTrue);
      expect(
        syncJobIsBackendBusy(status(error: 'Job timed out (background worker likely died)')),
        isTrue,
      );
    });

    test('does not hide typed zero-segment failures from retry accounting', () {
      expect(syncJobIsBackendBusy(status(reasonCode: 'sync_invalid_audio')), isFalse);
      expect(syncJobIsBackendBusy(status(reasonCode: 'sync_vad_failed')), isFalse);
    });
  });

  group('syncJobFailureIsPermanent', () {
    SyncJobStatusResponse job({required String status, String? reasonCode}) => SyncJobStatusResponse(
          jobId: 'synthetic-job',
          status: status,
          totalSegments: 1,
          processedSegments: 1,
          failedSegments: 1,
          reasonCode: reasonCode,
        );

    test('classifies an input-caused whole-job failure as permanent', () {
      for (final reasonCode in ['sync_invalid_audio', 'stt_invalid_input']) {
        expect(
          syncJobFailureIsPermanent(job(status: 'failed', reasonCode: reasonCode)),
          isTrue,
          reason: '$reasonCode cannot change for the same bytes',
        );
      }
    });

    test('keeps transient and capacity failures retryable', () {
      for (final reasonCode in [
        'sync_decode_failed',
        'sync_vad_failed',
        'stt_timeout',
        'stt_upstream_error',
        'sync_worker_stale',
        'backfill_paced',
        'backfill_capacity',
        null,
      ]) {
        expect(
          syncJobFailureIsPermanent(job(status: 'failed', reasonCode: reasonCode)),
          isFalse,
          reason: '${reasonCode ?? 'an unlabelled failure'} may succeed on a later attempt',
        );
      }
    });

    test('never condemns a batch that partly succeeded', () {
      expect(
        syncJobFailureIsPermanent(job(status: 'partial_failure', reasonCode: 'sync_invalid_audio')),
        isFalse,
        reason: 'segments that landed prove the batch is not wholly unreadable',
      );
      expect(syncJobFailureIsPermanent(job(status: 'completed')), isFalse);
      expect(syncJobFailureIsPermanent(job(status: 'processing', reasonCode: 'sync_invalid_audio')), isFalse);
    });
  });

  group('isAutoUploadEligible', () {
    Wal wal({required int retryCount, WalStatus status = WalStatus.miss}) => Wal(
          timerStart: 1789473658,
          codec: BleAudioCodec.opus,
          seconds: 1,
          status: status,
          storage: WalStorage.disk,
          filePath: 'audio.bin',
          retryCount: retryCount,
        );

    test('admits a recording with budget left', () {
      expect(isAutoUploadEligible(wal(retryCount: 0)), isTrue);
      expect(isAutoUploadEligible(wal(retryCount: walMaxAutoRetries - 1)), isTrue);
    });

    test('drops a recording whose auto-retry budget is spent', () {
      expect(isAutoUploadEligible(wal(retryCount: walMaxAutoRetries)), isFalse);
      expect(isAutoUploadEligible(wal(retryCount: walMaxAutoRetries + 5)), isFalse);
    });

    test('only ever admits retryable on-disk recordings', () {
      expect(isAutoUploadEligible(wal(retryCount: 0, status: WalStatus.uploaded)), isFalse);
      expect(isAutoUploadEligible(wal(retryCount: 0, status: WalStatus.synced)), isFalse);
      expect(isAutoUploadEligible(wal(retryCount: 0, status: WalStatus.outsideRecoveryWindow)), isFalse);
    });

    test('a spent budget is exactly what the sync row renders as failed', () {
      expect(wal(retryCount: walMaxAutoRetries).syncDisplayState, WalSyncDisplayState.failed);
      expect(wal(retryCount: walMaxAutoRetries - 1).syncDisplayState, WalSyncDisplayState.retrying);
    });
  });
}
