import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/batch_recording.dart';

/// Pure decision logic for the offline-fallback auto-upload flow: the gate
/// (custom-STT / auto-sync opt-out / single-flight) and the per-file selector +
/// backoff. These model exactly what `LocalRecordingsProvider._maybeAutoUpload`
/// drives, but stay free of the provider's heavy singletons so they run under
/// `bash test.sh` with no mocks.
void main() {
  const auto1 = 'audio_omibatchphoneauto_opus_fs320_16000_1_fs320_1720000001.bin';
  const auto2 = 'audio_omibatchphoneauto_opus_fs320_16000_1_fs320_1720000002.bin';
  const explicit = 'audio_omibatchphone_opus_fs320_16000_1_fs320_1720000003.bin';
  const limitless = 'audio_omibatchlimitless_opus_fs320_16000_1_fs320_1720000004.bin';

  group('canAutoUploadPhoneRecordings — gates', () {
    test('allows when opted in, not custom-STT, and idle', () {
      expect(
        canAutoUploadPhoneRecordings(useCustomStt: false, autoSyncOfflineRecordings: true, isUploading: false),
        isTrue,
      );
    });

    test('blocks custom-STT users (they sync manually)', () {
      expect(
        canAutoUploadPhoneRecordings(useCustomStt: true, autoSyncOfflineRecordings: true, isUploading: false),
        isFalse,
      );
    });

    test('blocks when the auto-sync opt-out is off', () {
      expect(
        canAutoUploadPhoneRecordings(useCustomStt: false, autoSyncOfflineRecordings: false, isUploading: false),
        isFalse,
      );
    });

    test('blocks while an upload is already in flight (single-flight)', () {
      expect(
        canAutoUploadPhoneRecordings(useCustomStt: false, autoSyncOfflineRecordings: true, isUploading: true),
        isFalse,
      );
    });
  });

  group('selectNextAutoPhoneUpload — selection', () {
    test('picks only auto-fallback recordings, in list order', () {
      final next = selectNextAutoPhoneUpload([explicit, auto1, auto2], busyNames: {}, failureCounts: {});
      expect(next, auto1);
    });

    test('never selects explicit / limitless / plain recordings', () {
      final next = selectNextAutoPhoneUpload(
        [explicit, limitless, 'audio_omibatch_opus_16000_1_fs160_1720000000.bin'],
        busyNames: {},
        failureCounts: {},
      );
      expect(next, isNull);
    });

    test('skips files that are uploading or processing (busy)', () {
      final next = selectNextAutoPhoneUpload([auto1, auto2], busyNames: {auto1}, failureCounts: {});
      expect(next, auto2);
    });

    test('returns null when every auto file is busy', () {
      final next = selectNextAutoPhoneUpload([auto1, auto2], busyNames: {auto1, auto2}, failureCounts: {});
      expect(next, isNull);
    });
  });

  group('selectNextAutoPhoneUpload — per-file backoff', () {
    test('skips a file at/over the failure cap, still picks a healthy one', () {
      final next = selectNextAutoPhoneUpload(
        [auto1, auto2],
        busyNames: {},
        failureCounts: {auto1: autoPhoneUploadMaxFailures},
      );
      expect(next, auto2);
    });

    test('a file just under the cap is still eligible', () {
      final next = selectNextAutoPhoneUpload(
        [auto1],
        busyNames: {},
        failureCounts: {auto1: autoPhoneUploadMaxFailures - 1},
      );
      expect(next, auto1);
    });

    test('returns null once all auto files hit the cap (retry only after relaunch)', () {
      final next = selectNextAutoPhoneUpload(
        [auto1, auto2],
        busyNames: {},
        failureCounts: {auto1: autoPhoneUploadMaxFailures, auto2: autoPhoneUploadMaxFailures},
      );
      expect(next, isNull);
    });

    test('cap is 3 consecutive failures', () {
      expect(autoPhoneUploadMaxFailures, 3);
    });
  });

  // Drives the provider's sequential-pass invariant against the pure pieces: a
  // file that keeps failing is retried at most `cap` times across passes, and a
  // healthy file is never blocked by a failing sibling.
  group('sequential pass simulation', () {
    test('a persistently-failing file backs off after exactly 3 attempts', () {
      final failureCounts = <String, int>{};
      var attempts = 0;
      // Simulate repeated triggers (connectivity flips): each pass picks the file
      // if still eligible; the upload "fails", incrementing the count.
      for (var pass = 0; pass < 10; pass++) {
        final next = selectNextAutoPhoneUpload([auto1], busyNames: {}, failureCounts: failureCounts);
        if (next == null) break;
        attempts++;
        failureCounts[next] = (failureCounts[next] ?? 0) + 1;
      }
      expect(attempts, autoPhoneUploadMaxFailures);
      expect(failureCounts[auto1], autoPhoneUploadMaxFailures);
    });

    test('a healthy sibling still uploads even while another file is capped', () {
      final failureCounts = {auto1: autoPhoneUploadMaxFailures};
      final uploaded = <String>{};
      // busyNames grows as files are accepted (deleted / queued), mirroring the
      // provider folding uploaded files out of the candidate set.
      final busy = <String>{};
      while (true) {
        final next = selectNextAutoPhoneUpload([auto1, auto2], busyNames: busy, failureCounts: failureCounts);
        if (next == null) break;
        uploaded.add(next);
        busy.add(next); // accepted → no longer selectable
      }
      expect(uploaded, {auto2});
    });
  });
}
