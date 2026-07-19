import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';

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
}
