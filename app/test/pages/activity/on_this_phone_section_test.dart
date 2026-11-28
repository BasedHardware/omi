// Activity's On this phone section and the bell it keeps lit (SCA-5226): recordings kept only on
// this phone are listed here, not on Home; Transcribe all sends what can be sent; the bell's
// warning dot stays lit for as long as any is here.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/activity/activity_bell_button.dart';
import 'package:omi/pages/activity/activity_seen.dart';
import 'package:omi/pages/activity/on_this_phone_section.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';

class _Recordings extends ChangeNotifier implements LocalRecordingsProvider {
  _Recordings(this._recordings);

  List<LocalRecording> _recordings;
  final sent = <String>[];
  LocalUploadOutcome answer = LocalUploadOutcome.started;

  @override
  List<LocalRecording> get recordings => _recordings;

  set recordings(List<LocalRecording> value) {
    _recordings = value;
    notifyListeners();
  }

  @override
  bool isPlaying(LocalRecording recording) => false;

  @override
  Future<LocalUploadOutcome> upload(LocalRecording rec) async {
    sent.add(rec.id);
    return answer;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

LocalRecording _rec(String id, LocalRecordingState state, {int minutesAgo = 10, bool retryCanHelp = true}) =>
    LocalRecording(
      fileName: id,
      filePath: '/tmp/$id.bin',
      timerStart: DateTime.now().subtract(Duration(minutes: minutesAgo)).millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      frameSize: 160,
      sizeBytes: 4096,
      seconds: 60,
      state: state,
      retryCanHelp: retryCanHelp,
    );

Widget _app(_Recordings recordings, Widget child) => ChangeNotifierProvider<LocalRecordingsProvider>.value(
      value: recordings,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(body: ListView(children: [child])),
      ),
    );

Future<void> _frames(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  test('lists every recording not being sent or processed, in the provider\'s newest-first order', () {
    final listed = onThisPhoneRecordings([
      _rec('new', LocalRecordingState.failed, minutesAgo: 5),
      _rec('sending', LocalRecordingState.uploading),
      _rec('old', LocalRecordingState.pending, minutesAgo: 60),
      _rec('processing', LocalRecordingState.processing),
    ]);
    expect([for (final r in listed) r.id], ['new', 'old']);
  });

  test('Transcribe all sends a waiting recording, and a failed one only when sending again can help', () {
    expect(sendableFromPhone(_rec('w', LocalRecordingState.pending), onDeviceActive: false), isTrue);
    expect(sendableFromPhone(_rec('w', LocalRecordingState.pending), onDeviceActive: true), isFalse,
        reason: 'on-device transcription owns the waiting ones');
    expect(sendableFromPhone(_rec('f', LocalRecordingState.failed), onDeviceActive: false), isTrue);
    expect(
        sendableFromPhone(_rec('t', LocalRecordingState.failed, retryCanHelp: false), onDeviceActive: false), isFalse);
  });

  testWidgets('the section counts them, Transcribe all sends the sendable ones, and nothing shows when empty',
      (tester) async {
    final recordings = _Recordings([
      _rec('waiting', LocalRecordingState.pending),
      _rec('refused', LocalRecordingState.failed, retryCanHelp: false),
      _rec('processing', LocalRecordingState.processing),
    ]);
    await tester.pumpWidget(_app(recordings, const OnThisPhoneSection()));
    await _frames(tester);
    expect(find.text('ON THIS PHONE'), findsOneWidget);
    expect(find.text('2 recordings, kept only on this phone'), findsOneWidget);
    expect(find.byKey(const ValueKey('activity_rec_processing')), findsNothing);

    await tester.tap(find.byKey(const Key('activity_transcribe_all')));
    await _frames(tester);
    expect(recordings.sent, ['waiting'], reason: 'a terminal refusal is not sent again');

    recordings.recordings = [_rec('refused', LocalRecordingState.failed, retryCanHelp: false)];
    await _frames(tester);
    expect(find.byKey(const Key('activity_transcribe_all')), findsNothing, reason: 'nothing left that can be sent');

    recordings.recordings = [_rec('processing', LocalRecordingState.processing)];
    await _frames(tester);
    expect(find.byKey(const Key('activity_on_this_phone')), findsNothing);
  });

  testWidgets('Transcribe all stops at the allowance and says so', (tester) async {
    final recordings = _Recordings([
      _rec('a', LocalRecordingState.pending, minutesAgo: 1),
      _rec('b', LocalRecordingState.pending, minutesAgo: 2),
    ])
      ..answer = LocalUploadOutcome.fairUseLimited;
    await tester.pumpWidget(_app(recordings, const OnThisPhoneSection()));
    await _frames(tester);
    await tester.tap(find.byKey(const Key('activity_transcribe_all')));
    await _frames(tester);
    expect(recordings.sent, ['a']);
  });

  testWidgets('the bell keeps its warning dot while any recording is only on this phone', (tester) async {
    final recordings = _Recordings([_rec('waiting', LocalRecordingState.pending)]);
    final store = PendingWorkStore(
      loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
    );
    addTearDown(store.dispose);
    final seen = ActivitySeen(read: () => 1, write: (_) {}, owner: () => 'owner');
    await tester.pumpWidget(_app(recordings, ActivityBellButton(seen: seen, pendingWork: store)));
    await _frames(tester);
    expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsOneWidget);
    seen.markSeen();
    await _frames(tester);
    expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsOneWidget,
        reason: 'seeing Activity does not clear it: the audio is still only here');
    recordings.recordings = [_rec('sending', LocalRecordingState.uploading)];
    await _frames(tester);
    expect(find.byKey(const ValueKey('home_activity_attention_dot')), findsNothing);
  });
}
