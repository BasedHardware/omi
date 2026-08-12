import 'package:flutter_test/flutter_test.dart';

import 'package:omi/providers/local_recordings_provider.dart';

void main() {
  group('Transcribe Later analytics policy', () {
    test('derives a bounded source from every batch recording family', () {
      expect(
        transcribeLaterRecordingSource(
          'audio_omibatchphone_opus_fs320_16000_1_fs320_1720000000.bin',
        ),
        'phone',
      );
      expect(
        transcribeLaterRecordingSource(
          'audio_omibatchphoneauto_opus_fs320_16000_1_fs320_1720000000.bin',
        ),
        'phone',
      );
      expect(
        transcribeLaterRecordingSource(
          'audio_omibatchlimitless_opus_fs320_16000_1_fs320_1720000000.bin',
        ),
        'limitless',
      );
      expect(
        transcribeLaterRecordingSource(
          'audio_omibatch_opus_16000_1_fs160_1720000000.bin',
        ),
        'omi',
      );
    });

    test('maps accepted and failed upload attempts to closed outcomes', () {
      expect(
        transcribeLaterUploadAnalyticsOutcome(LocalUploadOutcome.started),
        (success: true, outcome: 'accepted'),
      );
      expect(
        transcribeLaterUploadAnalyticsOutcome(
          LocalUploadOutcome.fairUseLimited,
        ),
        (success: false, outcome: 'fair_use_limited'),
      );
      expect(
        transcribeLaterUploadAnalyticsOutcome(LocalUploadOutcome.backendBusy),
        (success: false, outcome: 'backend_busy'),
      );
      expect(transcribeLaterUploadAnalyticsOutcome(LocalUploadOutcome.failed), (
        success: false,
        outcome: 'upload_failed',
      ));
      expect(transcribeLaterUploadAnalyticsOutcome(LocalUploadOutcome.busy), (
        success: false,
        outcome: 'busy',
      ));
    });
  });
}
