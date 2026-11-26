import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/wal_delete_confirmation.dart';
import 'package:omi/services/wals/wal.dart';

/// Which delete confirmation each sync state gets. Only audio the server already holds may get the
/// "removes the phone's copy" message; anything else would lose audio outright and keeps the warning.
void main() {
  final en = lookupAppLocalizations(const Locale('en'));
  const fallback = 'fallback warning';

  Wal wal(WalSyncDisplayState state, {int offset = 0}) {
    final w = Wal(timerStart: 1700000000 + offset, codec: BleAudioCodec.opus, seconds: 30, status: WalStatus.miss);
    switch (state) {
      case WalSyncDisplayState.synced:
        w.status = WalStatus.synced;
      case WalSyncDisplayState.uploaded:
        w.status = WalStatus.uploaded;
        w.jobId = 'job';
      case WalSyncDisplayState.syncing:
        w.isSyncing = true;
      case WalSyncDisplayState.waiting:
        break;
      case WalSyncDisplayState.retrying:
        w.retryCount = 1;
      case WalSyncDisplayState.failed:
        w.retryCount = walMaxAutoRetries;
      case WalSyncDisplayState.corrupted:
        w.status = WalStatus.corrupted;
      case WalSyncDisplayState.outsideRecoveryWindow:
        w.status = WalStatus.outsideRecoveryWindow;
      case WalSyncDisplayState.unsupportedAudio:
        w.status = WalStatus.unsupportedAudio;
      case WalSyncDisplayState.uploadRejected:
        w.status = WalStatus.uploadRejected;
    }
    expect(w.syncDisplayState, state, reason: 'fixture must produce $state');
    return w;
  }

  // These cases pin #25676's phone-copy wording, which applies while the server's owner-cancel
  // switch is off; the cancel-on cases are at the end.
  ({String title, String message}) confirm(List<Wal> wals, {String notUploaded = fallback, bool paused = true}) =>
      walDeleteConfirmation(en, wals, notUploadedMessage: notUploaded, serverCancelPaused: paused);

  final processingCopy = (title: en.deleteWhileProcessingTitle, message: en.deleteWhileProcessingMessage);
  final keepsConversation = (title: en.deleteRecording, message: en.deleteRecordingKeepsConversation);
  final warning = (title: en.deleteRecording, message: fallback);

  test('the processing copy does not promise the audio survives', () {
    expect(
      en.deleteWhileProcessingMessage,
      "This recording is already uploaded and Omi is processing it. Deleting it here removes the phone's copy. "
      "If processing fails, Omi can't retry from this phone.",
    );
  });

  for (final state in WalSyncDisplayState.values) {
    final expected = switch (state) {
      WalSyncDisplayState.uploaded => processingCopy,
      WalSyncDisplayState.synced => keepsConversation,
      _ => warning,
    };
    test('a single $state file gets the correct confirmation', () {
      expect(confirm([wal(state)]), expected);
    });
  }

  test('uploaded with already processed files explains that conversations stay', () {
    expect(
        confirm([wal(WalSyncDisplayState.uploaded), wal(WalSyncDisplayState.synced, offset: 30)]), keepsConversation);
  });

  for (final other in WalSyncDisplayState.values
      .where((s) => s != WalSyncDisplayState.uploaded && s != WalSyncDisplayState.synced)) {
    test('uploaded mixed with a $other file keeps the warning', () {
      expect(confirm([wal(WalSyncDisplayState.uploaded), wal(other, offset: 30)]), warning);
    });
  }

  test('a refused member (uploadRejected, outsideRecoveryWindow) beside uploaded keeps the warning', () {
    for (final refused in [WalSyncDisplayState.uploadRejected, WalSyncDisplayState.outsideRecoveryWindow]) {
      expect(confirm([wal(refused), wal(WalSyncDisplayState.uploaded, offset: 30)]), warning, reason: '$refused');
    }
  });

  test('a fully processed selection explains that conversations stay', () {
    expect(confirm([wal(WalSyncDisplayState.synced), wal(WalSyncDisplayState.synced, offset: 30)]), keepsConversation);
  });

  test("the detail page's fallback string is used when not everything is on the server", () {
    expect(
      confirm([wal(WalSyncDisplayState.waiting)], notUploaded: en.deleteRecordingConfirmation),
      (title: en.deleteRecording, message: en.deleteRecordingConfirmation),
    );
    expect(
      confirm([wal(WalSyncDisplayState.uploaded)], notUploaded: en.deleteRecordingConfirmation),
      processingCopy,
    );
  });

  group('with owner cancel on', () {
    final erased = (title: en.deleteFromServerTitle, message: en.deleteFromServerMessage);

    test('an uploaded recording says the server copy is cancelled and erased too', () {
      expect(confirm([wal(WalSyncDisplayState.uploaded)], paused: false), erased);
      expect(
        confirm([wal(WalSyncDisplayState.uploaded), wal(WalSyncDisplayState.synced, offset: 30)], paused: false),
        keepsConversation,
      );
      expect(en.deleteFromServerMessage, contains("permanently erases the copy on Omi's servers"));
    });

    test('anything not yet on the server keeps the warning either way', () {
      expect(confirm([wal(WalSyncDisplayState.uploaded), wal(WalSyncDisplayState.waiting, offset: 30)], paused: false),
          warning);
      expect(confirm([wal(WalSyncDisplayState.synced)], paused: false), keepsConversation);
    });

    test('an uploaded row with no job handle cannot be cancelled and keeps the phone-copy wording', () {
      expect(confirm([wal(WalSyncDisplayState.uploaded)..jobId = null], paused: false), processingCopy);
      expect(
        confirm([wal(WalSyncDisplayState.uploaded), wal(WalSyncDisplayState.uploaded, offset: 30)..jobId = null],
            paused: false),
        processingCopy,
      );
    });

    test('every locale carries both uploaded copies', () {
      for (final locale in AppLocalizations.supportedLocales) {
        final l = lookupAppLocalizations(locale);
        expect(l.deleteFromServerMessage, isNotEmpty, reason: '$locale');
        expect(l.deleteWhileProcessingMessage, isNotEmpty, reason: '$locale');
        expect(l.deleteFromServerMessage, isNot(l.deleteWhileProcessingMessage), reason: '$locale');
      }
    });
  });
}
