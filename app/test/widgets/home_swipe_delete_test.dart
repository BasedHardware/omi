// Home's one swipe-to-delete (SCA-5226): a long swipe asks, yes deletes, no closes the row; a busy
// recording on this phone cannot be swiped; and its Retry shows only when sending again can help.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/home/home_swipe_delete.dart';
import 'package:omi/pages/conversations/widgets/recording_list_item.dart';
import 'package:omi/providers/local_recordings_provider.dart';

class _Recordings extends ChangeNotifier implements LocalRecordingsProvider {
  final deleted = <String>[];

  @override
  bool isPlaying(LocalRecording recording) => false;

  @override
  Future<void> delete(LocalRecording recording) async => deleted.add(recording.id);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

LocalRecording _recording(LocalRecordingState state, {bool retryCanHelp = true}) => LocalRecording(
      fileName: 'r1',
      filePath: '/tmp/r1.bin',
      timerStart: DateTime(2026, 11, 27, 9).millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      frameSize: 160,
      sizeBytes: 4096,
      seconds: 62,
      state: state,
      retryCanHelp: retryCanHelp,
    );

Widget _app(Widget child, {LocalRecordingsProvider? recordings}) =>
    ChangeNotifierProvider<LocalRecordingsProvider>.value(
      value: recordings ?? _Recordings(),
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(body: ListView(children: [child])),
      ),
    );

/// Pumps fixed frames: a busy row's spinner never settles.
Future<void> _frames(WidgetTester tester) async {
  for (var i = 0; i < 6; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

/// A swipe past the point where letting go asks straight away.
Future<void> _swipeFar(WidgetTester tester, Finder row) async {
  final gesture = await tester.startGesture(tester.getCenter(row));
  for (var i = 0; i < 25; i++) {
    await gesture.moveBy(const Offset(-20, 0));
    await tester.pump(const Duration(milliseconds: 16));
  }
  await gesture.up();
  await _frames(tester);
}

void main() {
  setUp(() {
    final view = TestWidgetsFlutterBinding.instance.platformDispatcher.views.first;
    view.physicalSize = const Size(800, 1200);
    view.devicePixelRatio = 1;
  });

  testWidgets('a long swipe asks; yes deletes, no closes the row', (tester) async {
    var answer = false;
    var asked = 0;
    var deleted = 0;
    await tester.pumpWidget(_app(HomeSwipeDelete(
      enabled: true,
      confirm: (_) async {
        asked++;
        return answer;
      },
      onDeleted: () => deleted++,
      child: const SizedBox(
          key: ValueKey('card'), width: double.infinity, height: 72, child: ColoredBox(color: Colors.white)),
    )));
    final card = find.byKey(const ValueKey('card'));
    final rest = tester.getTopLeft(card);

    await _swipeFar(tester, card);
    expect(asked, 1);
    expect(deleted, 0);
    expect(tester.getTopLeft(card), rest, reason: 'a refused delete closes the row');

    answer = true;
    await _swipeFar(tester, card);
    expect(asked, 2);
    expect(deleted, 1);
  });

  testWidgets('a disabled row does not move', (tester) async {
    var asked = 0;
    await tester.pumpWidget(_app(HomeSwipeDelete(
      enabled: false,
      confirm: (_) async => (asked++) >= 0,
      onDeleted: () {},
      child: const SizedBox(
          key: ValueKey('card'), width: double.infinity, height: 72, child: ColoredBox(color: Colors.white)),
    )));
    final card = find.byKey(const ValueKey('card'));
    final rest = tester.getTopLeft(card);
    await _swipeFar(tester, card);
    expect(tester.getTopLeft(card), rest);
    expect(asked, 0);
  });

  group('a recording on this phone', () {
    testWidgets('confirms before deleting, with no Undo', (tester) async {
      final recordings = _Recordings();
      await tester.pumpWidget(
          _app(RecordingListItem(recording: _recording(LocalRecordingState.failed)), recordings: recordings));
      await _swipeFar(tester, find.byKey(const ValueKey('rec_r1')));
      expect(find.text('This cannot be undone.'), findsOneWidget, reason: 'it confirms first');
      await tester.tap(find.text('Delete').last);
      await _frames(tester);
      expect(recordings.deleted, ['r1']);
      expect(find.text('Undo'), findsNothing);
    });

    testWidgets('cannot be swiped while the server is working on it', (tester) async {
      final recordings = _Recordings();
      await tester.pumpWidget(
          _app(RecordingListItem(recording: _recording(LocalRecordingState.processing)), recordings: recordings));
      final row = find.byKey(const ValueKey('rec_r1'));
      final rest = tester.getTopLeft(row);
      await _swipeFar(tester, row);
      expect(tester.getTopLeft(row), rest);
      expect(find.byType(Dialog), findsNothing);
    });

    testWidgets('offers Retry only when sending again can help', (tester) async {
      await tester.pumpWidget(_app(RecordingListItem(recording: _recording(LocalRecordingState.failed))));
      expect(find.byKey(const ValueKey('rec_retry_r1')), findsOneWidget);
      await tester
          .pumpWidget(_app(RecordingListItem(recording: _recording(LocalRecordingState.failed, retryCanHelp: false))));
      expect(find.byKey(const ValueKey('rec_retry_r1')), findsNothing);
      expect(find.byKey(const ValueKey('rec_play_r1')), findsOneWidget, reason: 'a terminal refusal still plays');
    });
  });
}
