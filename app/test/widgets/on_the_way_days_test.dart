import 'package:omi/services/wals/wal_derived_sync_views.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart' show BleAudioCodec;
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';

/// On the Way, option B: a headline with how much is catching up and a thin bar, one row per
/// local day with its totals and a quiet status, a footnote, and a plain support list.

class _FakeSync extends ChangeNotifier with WalDerivedSyncViews implements SyncProvider {
  _FakeSync(this.wals, {this.state = const SyncState()});

  final List<Wal> wals;
  final SyncState state;

  @override
  SyncState get syncState => state;
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

Wal _wal(DateTime start, int seconds, WalStatus status, {String? rejectionReason}) => Wal(
      timerStart: start.millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: seconds,
      status: status,
      storage: WalStorage.disk,
      device: 'phone',
      uploadRejectionReason: rejectionReason,
    );

Future<void> _pump(WidgetTester tester, List<Wal> wals,
    {double textScale = 1, SyncState state = const SyncState(), bool online = true}) async {
  final sync = _FakeSync(wals, state: state);
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<SyncProvider>.value(value: sync),
        ChangeNotifierProvider<ConnectivityProvider>.value(value: _Connectivity(online)),
      ],
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

class _Connectivity extends ChangeNotifier implements ConnectivityProvider {
  _Connectivity(this.isConnected);

  @override
  final bool isConnected;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// A support row's first line; intl separates the time from AM/PM with a narrow no-break space.
Finder _row(String text) =>
    find.byWidgetPredicate((w) => w is Text && w.data?.replaceAll('\u202f', ' ') == text, description: text);

Finder _day(String date) => find.byKey(Key('on_the_way_day_$date'));

/// A day row's title, subtitle and status, in reading order.
List<String> _dayTexts(WidgetTester tester, String date) =>
    [for (final t in tester.widgetList<Text>(find.descendant(of: _day(date), matching: find.byType(Text)))) t.data!];

Future<void> _openSupport(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('on_the_way_details_for_support')));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('one row per local day: totals on the subtitle, a quiet status on the right', (tester) async {
    await _pump(tester, [
      // Starts 11:50 PM yesterday and runs 20 minutes past midnight: it stays on yesterday.
      _wal(DateTime(2026, 10, 17, 23, 50), 20 * 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 18, 0, 30), 5 * 60, WalStatus.miss)..isSyncing = true,
      _wal(DateTime(2026, 10, 18, 8, 15), 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 16, 14), 10 * 60, WalStatus.miss),
      _wal(DateTime(2026, 10, 14, 9), 30 * 60, WalStatus.miss),
    ]);

    expect(find.text('1h 6m catching up'), findsOneWidget);
    expect(find.text('Uploads by itself. Conversations fill in as it lands.'), findsOneWidget);
    expect(_dayTexts(tester, '2026-10-18'), ['Today', '2 recordings · 6m', 'Uploading']);
    expect(_dayTexts(tester, '2026-10-17'), ['Yesterday', '1 recording · 20m', 'Transcribing…']);
    // Uploads go oldest first: the oldest waiting day is next, the rest wait their turn.
    expect(_dayTexts(tester, '2026-10-16').last, 'Queued');
    expect(_dayTexts(tester, '2026-10-14').last, 'Next');
    expect(tester.getTopLeft(_day('2026-10-18')).dy, lessThan(tester.getTopLeft(_day('2026-10-17')).dy));
    // Recordings are not rows on this page.
    expect(_row('8:15 AM · 1m'), findsNothing);
    expect(
      tester.getTopLeft(find.byKey(const Key('on_the_way_footnote'))).dy,
      greaterThan(tester.getTopLeft(_day('2026-10-14')).dy),
    );
  });

  testWidgets('the bar fills with audio already on the server', (tester) async {
    await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8), 30 * 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 17, 7), 90 * 60, WalStatus.miss),
    ]);
    final bar = tester.widget<LinearProgressIndicator>(find.byKey(const Key('on_the_way_progress')));
    expect(bar.value, 0.25);
  });

  testWidgets('offline, the line says it uploads once back online', (tester) async {
    await _pump(tester, [_wal(DateTime(2026, 10, 18, 8), 60, WalStatus.miss)], online: false);
    expect(find.text("Uploads by itself once you're back online. Conversations fill in as it lands."), findsOneWidget);
  });

  testWidgets('failed and refused recordings are never rows, actions or counts', (tester) async {
    await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 18, 7), 3 * 60, WalStatus.outsideRecoveryWindow),
      _wal(DateTime(2026, 10, 18, 6), 2 * 60, WalStatus.uploadRejected,
          rejectionReason: WalUploadRejection.invalidCaptureTime),
      _wal(DateTime(2026, 10, 15, 9), 60, WalStatus.unsupportedAudio),
    ]);
    expect(find.text('4m catching up'), findsOneWidget);
    expect(_dayTexts(tester, '2026-10-18'), ['Today', '1 recording · 4m', 'Transcribing…']);
    expect(_day('2026-10-15'), findsNothing);
    expect(find.textContaining('need attention'), findsNothing);
    expect(find.text('Try Again'), findsNothing);
    expect(find.text('Delete'), findsNothing);
    expect(
        find.text(
            "Recordings that fail keep retrying in the background. Anything we can't transcribe is reported to us automatically."),
        findsOneWidget);
  });

  testWidgets('Details for support lists every recording with its reason tokens and no buttons', (tester) async {
    await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 18, 7), 3 * 60, WalStatus.outsideRecoveryWindow),
      _wal(DateTime(2026, 10, 18, 6), 2 * 60, WalStatus.uploadRejected,
          rejectionReason: WalUploadRejection.invalidCaptureTime)
        ..uploadRejectionStatusCode = 400,
    ]);
    await _openSupport(tester);

    expect(find.text('Details for support'), findsWidgets);
    expect(_row('8:00 AM · 4m'), findsOneWidget);
    expect(_row('7:00 AM · 3m'), findsOneWidget);
    expect(_row('6:00 AM · 2m'), findsOneWidget);
    expect(find.text('Invalid recording date'), findsOneWidget);
    expect(find.text('uploadRejected · invalid_capture_time · 400'), findsOneWidget);
    expect(find.text('outsideRecoveryWindow'), findsOneWidget);
    expect(find.text('Try Again'), findsNothing);
    expect(find.text('Delete'), findsNothing);
    // The Offline Sync page stays one tap further, counting only what it lists as attention.
    expect(find.byKey(const Key('on_the_way_sync_details')), findsOneWidget);
    expect(find.text('1 recording need attention'), findsOneWidget);
  });

  testWidgets('a recording stamped before 2024 joins the No date row instead of a bogus day', (tester) async {
    await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.uploaded),
      // A pendant clock that was never set: 1985-09-05 16:17 local.
      _wal(DateTime(1985, 9, 5, 16, 17), 3 * 60, WalStatus.miss),
    ]);
    expect(_day('1985-09-05'), findsNothing);
    expect(find.textContaining('1985'), findsNothing);
    expect(_dayTexts(tester, 'undated'), ['No date', '1 recording · 3m', 'Next']);
    expect(find.text('7m catching up'), findsOneWidget);
  });

  testWidgets('a wearable source outlives its exhausted phone copy: support shows the worse state', (tester) async {
    // A device drain copies audio to the phone piece by piece; copy and source share the
    // recording id. The phone copy exhausted its retries while the audio still sits on the
    // wearable: support reads it as failed (its worst part), never merely syncing.
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
    // The page counts the audio still on the wearable.
    expect(_dayTexts(tester, '2026-10-18'), ['Today', '1 recording · 4m', 'Next']);
    await _openSupport(tester);
    expect(_row('8:00 AM · 4m'), findsOneWidget);
    expect(find.text('Failed — tap Retry'), findsOneWidget);
  });

  testWidgets('rows and header grow with the largest text instead of clipping', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await _pump(
      tester,
      [
        _wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.miss)..isSyncing = true,
        _wal(DateTime(2026, 10, 15, 10), 30 * 60, WalStatus.miss),
      ],
      textScale: 3.1,
    );
    expect(tester.takeException(), isNull);
    for (final day in ['2026-10-18', '2026-10-15']) {
      await tester.scrollUntilVisible(_day(day), 200);
      expect(tester.getSize(_day(day)).height, greaterThanOrEqualTo(44));
      final subtitle = tester.getRect(find.descendant(of: _day(day), matching: find.byType(Text)).at(1));
      expect(tester.getRect(_day(day)).contains(subtitle.bottomLeft - const Offset(0, 1)), isTrue);
    }
    final link = find.byKey(const Key('on_the_way_details_for_support'));
    await tester.scrollUntilVisible(link, 200);
    expect(tester.takeException(), isNull);
    expect(tester.getSize(link).height, greaterThanOrEqualTo(44));
  });

  testWidgets('nothing on the way reads as all synced, with no day rows', (tester) async {
    await _pump(tester, [_wal(DateTime(2026, 10, 18, 8), 60, WalStatus.synced)]);
    expect(find.text('All recordings are synced'), findsOneWidget);
    expect(find.byKey(const Key('on_the_way_day_2026-10-18')), findsNothing);
    expect(find.textContaining('catching up'), findsNothing);
  });

  testWidgets('a quiet failure alone is never all synced, and support still reaches it', (tester) async {
    await _pump(tester, [_wal(DateTime(2026, 10, 18, 8), 60, WalStatus.uploadRejected)]);
    expect(find.text('All recordings are synced'), findsNothing);
    expect(find.textContaining('catching up'), findsNothing);
    await _openSupport(tester);
    expect(_row('8:00 AM · 1m'), findsOneWidget);
  });

  testWidgets('grouped chunks with gaps total only positive audio duration', (tester) async {
    await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8, 0), 5, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 18, 8, 1), 5, WalStatus.uploaded),
      _wal(DateTime(2026, 10, 18, 8, 2), 5, WalStatus.uploaded),
    ]);
    expect(find.text('15s catching up'), findsOneWidget);
    expect(_dayTexts(tester, '2026-10-18')[1], '1 recording · 15s');
    expect(find.textContaining('2m 5s'), findsNothing);
  });
}
