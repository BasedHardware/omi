import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart' show BleAudioCodec;
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/ui.dart';

/// On the Way groups recordings by the local day they started: a summary line, then one pinned
/// header per day with its totals. Today opens by default; older days fold to their totals.

class _FakeSync extends ChangeNotifier implements SyncProvider {
  _FakeSync(this.wals);

  final List<Wal> wals;

  @override
  SyncState get syncState => const SyncState();
  @override
  bool get isSyncing => false;
  @override
  bool get isRateLimited => false;
  @override
  List<Wal> get allWals => wals;
  @override
  List<Wal> get displaySortedWals => [...wals]..sort((a, b) => b.timerStart.compareTo(a.timerStart));
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// 9:00 AM local on a Sunday; every fixture is local time, so the day split does not depend on the
/// machine's time zone.
final _now = DateTime(2026, 10, 18, 9);

Wal _wal(DateTime start, int seconds, WalStatus status) => Wal(
      timerStart: start.millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: seconds,
      status: status,
      storage: WalStorage.disk,
      device: 'phone',
    );

Future<void> _pump(WidgetTester tester, List<Wal> wals, {double textScale = 1}) async {
  final sync = _FakeSync(wals);
  await tester.pumpWidget(
    ChangeNotifierProvider<SyncProvider>.value(
      value: sync,
      child: MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: OnTheWayPage(multiFileSync: true, clock: () => _now),
      ),
    ),
  );
  await tester.pump();
}

/// A row's first line; intl separates the time from AM/PM with a narrow no-break space.
Finder _row(String text) =>
    find.byWidgetPredicate((w) => w is Text && w.data?.replaceAll('\u202f', ' ') == text, description: text);

Finder _day(String date) => find.byKey(Key('on_the_way_day_$date'));

/// The header's second line: totals, then the exceptions.
String _headerLine(WidgetTester tester, String date) {
  final text = tester.widget<Text>(find.descendant(of: _day(date), matching: find.byType(Text)).at(1));
  return text.textSpan!.toPlainText();
}

void main() {
  setUp(OnTheWayPage.resetFolds);

  testWidgets('groups by the local day a recording started, across midnight', (tester) async {
    await _pump(tester, [
      // Starts 11:50 PM yesterday and runs 20 minutes past midnight: it stays on yesterday.
      _wal(DateTime(2026, 10, 17, 23, 50), 20 * 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 18, 0, 30), 5 * 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 18, 8, 15), 60, WalStatus.uploaded),
    ]);

    expect(find.descendant(of: _day('2026-10-18'), matching: find.text('Today')), findsOneWidget);
    expect(find.descendant(of: _day('2026-10-17'), matching: find.text('Yesterday')), findsOneWidget);
    expect(_headerLine(tester, '2026-10-18'), '2 recordings · 6m');
    expect(_headerLine(tester, '2026-10-17'), '1 recording · 20m');
    // Today is open, newest first; yesterday is folded to its totals.
    expect(_row('8:15 AM · 1m'), findsOneWidget);
    expect(_row('12:30 AM · 5m'), findsOneWidget);
    expect(tester.getTopLeft(_row('8:15 AM · 1m')).dy, lessThan(tester.getTopLeft(_row('12:30 AM · 5m')).dy));
    expect(_row('11:50 PM · 20m'), findsNothing);
    // Days run newest first, and Sync Details stays the last row.
    expect(tester.getTopLeft(_day('2026-10-18')).dy, lessThan(tester.getTopLeft(_day('2026-10-17')).dy));
    expect(
      tester.getTopLeft(find.byKey(const Key('on_the_way_sync_details'))).dy,
      greaterThan(tester.getTopLeft(_day('2026-10-17')).dy),
    );
  });

  testWidgets('a recording stamped before 2024 lists without a time instead of on a bogus day', (tester) async {
    await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.uploaded),
      // A pendant clock that was never set: 1985-09-05 16:17 local.
      _wal(DateTime(1985, 9, 5, 16, 17), 3 * 60, WalStatus.uploaded),
    ]);

    expect(_row('8:00 AM · 4m'), findsOneWidget);
    // No 1985 day header, and no time-of-day row for the bogus clock value.
    expect(_day('1985-09-05'), findsNothing);
    expect(find.textContaining('1985'), findsNothing);
    expect(_row('4:17 PM · 3m'), findsNothing);
    // The recording still lists — undated, like server work without a start:
    // its row carries only the stage label, so "Transcribing…" appears twice.
    expect(find.text('Transcribing…'), findsNWidgets(2));
  });

  testWidgets('the summary and day headers total recordings and name only the exceptions', (tester) async {
    await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 18, 7), 2 * 60, WalStatus.miss),
      _wal(DateTime(2026, 10, 18, 6), 3 * 60, WalStatus.outsideRecoveryWindow),
      _wal(DateTime(2026, 10, 15, 10), 30 * 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 15, 9), 60, WalStatus.unsupportedAudio),
    ]);

    expect(find.text('5 recordings · 40m on the way'), findsOneWidget);
    // Transcribing is the normal state and is never counted.
    expect(find.text('1 uploading · 2 need attention'), findsOneWidget);
    expect(_headerLine(tester, '2026-10-18'), '3 recordings · 9m · 1 uploading · 1 needs attention');
    expect(_headerLine(tester, '2026-10-15'), '2 recordings · 31m · 1 needs attention');

    // Only the attention count is in warning colour.
    final spans = tester
        .widget<Text>(find.descendant(of: _day('2026-10-18'), matching: find.byType(Text)).at(1))
        .textSpan! as TextSpan;
    final warning = spans.children!.cast<TextSpan>().where((s) => s.style?.color == OmiColors.warning).toList();
    expect(warning.map((s) => s.text), [' · 1 needs attention']);

    // A refused row says why in the Offline Sync page's words, in warning colour, with a chevron.
    final reason = tester.widget<Text>(find.text("Too old to sync — Omi can't accept it"));
    expect(reason.style?.color, OmiColors.warning);
    // Sync Details still counts the refused recordings.
    expect(find.text('2 recordings need attention'), findsOneWidget);
  });

  testWidgets('a wearable source outlives its exhausted phone copy: the block shows the worse state', (tester) async {
    // A device drain copies audio to the phone piece by piece; copy and source
    // share the recording id. Here the phone copy exhausted its retries while
    // the audio still sits on the wearable: the recording must read as needing
    // attention (its worst part), never as merely syncing (its healthy part).
    Wal drainPiece(DateTime start, int seconds, {WalStorage? original, int retries = 0}) => Wal(
          timerStart: start.millisecondsSinceEpoch ~/ 1000,
          codec: BleAudioCodec.opus,
          seconds: seconds,
          status: WalStatus.miss,
          storage: original == null ? WalStorage.sdcard : WalStorage.disk,
          originalStorage: original,
          device: 'pendant',
          retryCount: retries,
        );
    final start = DateTime(2026, 10, 18, 8);
    await _pump(tester, [
      drainPiece(start, 4 * 60, original: WalStorage.sdcard, retries: 3),
      drainPiece(start, 4 * 60),
    ]);

    // One recording, shown once — as refused, not as waiting.
    expect(_row('8:00 AM · 4m'), findsOneWidget);
    expect(_headerLine(tester, '2026-10-18'), '1 recording · 4m · 1 needs attention');
    expect(find.text('Failed — tap Retry'), findsOneWidget);
    expect(find.text('1 recording need attention'), findsOneWidget);
    expect(find.text('2 recordings need attention'), findsNothing);
  });

  testWidgets('a day opens and folds on tap, and stays that way for the session', (tester) async {
    final wals = [
      _wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 16, 14, 5), 7 * 60, WalStatus.uploaded),
    ];
    await _pump(tester, wals);
    expect(_row('8:00 AM · 4m'), findsOneWidget);
    expect(_row('2:05 PM · 7m'), findsNothing);
    expect(find.descendant(of: _day('2026-10-16'), matching: find.byIcon(Icons.expand_more)), findsOneWidget);

    await tester.tap(_day('2026-10-16'));
    await tester.pump();
    expect(_row('2:05 PM · 7m'), findsOneWidget);
    expect(find.descendant(of: _day('2026-10-16'), matching: find.byIcon(Icons.expand_less)), findsOneWidget);

    await tester.tap(_day('2026-10-18'));
    await tester.pump();
    expect(_row('8:00 AM · 4m'), findsNothing);

    // Leaving and coming back keeps the folds; only a new session opens on Today again.
    await tester.pumpWidget(const SizedBox());
    await _pump(tester, wals);
    expect(_row('8:00 AM · 4m'), findsNothing);
    expect(_row('2:05 PM · 7m'), findsOneWidget);

    OnTheWayPage.resetFolds();
    await tester.pumpWidget(const SizedBox());
    await _pump(tester, wals);
    expect(_row('8:00 AM · 4m'), findsOneWidget);
    expect(_row('2:05 PM · 7m'), findsNothing);
  });

  testWidgets('a day header reports its fold state to accessibility', (tester) async {
    final handle = tester.ensureSemantics();
    await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8), 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 16, 8), 60, WalStatus.uploaded),
    ]);
    expect(tester.getSemantics(_day('2026-10-18')), isSemantics(isHeader: true, isExpanded: true));
    expect(tester.getSemantics(_day('2026-10-16')), isSemantics(isHeader: true, isExpanded: false));
    await tester.tap(_day('2026-10-16'));
    await tester.pump();
    expect(tester.getSemantics(_day('2026-10-16')), isSemantics(isHeader: true, isExpanded: true));
    handle.dispose();
  });

  testWidgets('pinned headers grow with large text instead of clipping', (tester) async {
    await _pump(
      tester,
      [
        _wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.miss),
        _wal(DateTime(2026, 10, 15, 10), 30 * 60, WalStatus.outsideRecoveryWindow),
      ],
      textScale: 2,
    );
    expect(tester.takeException(), isNull);
    expect(tester.getSize(_day('2026-10-18')).height, greaterThan(44 * 1.5));
    final title = tester.getRect(find.descendant(of: _day('2026-10-15'), matching: find.byType(Text)).at(1));
    expect(tester.getRect(_day('2026-10-15')).contains(title.bottomLeft - const Offset(0, 1)), isTrue);
  });

  testWidgets('nothing on the way reads as all synced, with no day headers', (tester) async {
    await _pump(tester, [_wal(DateTime(2026, 10, 18, 8), 60, WalStatus.synced)]);
    expect(find.text('All recordings are synced'), findsOneWidget);
    expect(find.byKey(const Key('on_the_way_day_2026-10-18')), findsNothing);
    expect(find.textContaining('on the way'), findsNothing);
  });

  testWidgets('grouped chunks with gaps display only positive audio duration in summary, day, and row', (tester) async {
    await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8, 0), 5, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 18, 8, 1), 5, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 18, 8, 2), 5, WalStatus.uploaded),
    ]);

    expect(find.text('1 recording · 15s on the way'), findsOneWidget);
    expect(_headerLine(tester, '2026-10-18'), '1 recording · 15s');
    expect(_row('8:00 AM · 15s'), findsOneWidget);
    expect(find.textContaining('2m 5s'), findsNothing);
  });
}
