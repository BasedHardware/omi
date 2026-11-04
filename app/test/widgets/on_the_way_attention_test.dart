import 'package:omi/services/wals/wal_derived_sync_views.dart';
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

/// Option B: failures and refusals recover in the background. Neither On the Way nor its
/// support details offers Retry or Delete; those stay on the Offline Sync page.

class _FakeSync extends ChangeNotifier with WalDerivedSyncViews implements SyncProvider {
  _FakeSync(this.wals);

  final List<Wal> wals;
  final retried = <Wal>[];
  final deleted = <Wal>[];

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
  Future<void> syncWal(Wal wal) async => retried.add(wal);
  @override
  Future<void> deleteWal(Wal wal) async => deleted.add(wal);

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

final _now = DateTime(2026, 10, 18, 9);

Wal _wal(
  DateTime start,
  int seconds,
  WalStatus status, {
  String? rejectionReason,
}) =>
    Wal(
      timerStart: start.millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: seconds,
      status: status,
      storage: WalStorage.disk,
      device: 'phone',
      uploadRejectionReason: rejectionReason,
    );

Future<_FakeSync> _pump(WidgetTester tester, List<Wal> wals) async {
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
        home: OnTheWayPage(multiFileSync: true, clock: () => _now),
      ),
    ),
  );
  await tester.pump();
  return sync;
}

/// A row's first line; intl separates the time from AM/PM with a narrow no-break space.
Finder _row(String text) =>
    find.byWidgetPredicate((w) => w is Text && w.data?.replaceAll('\u202f', ' ') == text, description: text);

Future<void> _openSupport(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('on_the_way_details_for_support')));
  await tester.pumpAndSettle();
}

/// No recovery gesture on either view, and the audio is never touched.
Future<void> _expectNoActions(WidgetTester tester, _FakeSync sync, int walCount) async {
  for (var view = 0; view < 2; view++) {
    expect(find.text('Try Again'), findsNothing);
    expect(find.text('Delete'), findsNothing);
    if (view == 0) await _openSupport(tester);
  }
  expect(sync.retried, isEmpty);
  expect(sync.deleted, isEmpty);
  expect(sync.allWals, hasLength(walCount));
}

void main() {
  testWidgets('deterministic refusals stay off the page and quiet in support', (tester) async {
    final sync = await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8), 240, WalStatus.uploadRejected,
          rejectionReason: WalUploadRejection.invalidCaptureTime),
      _wal(DateTime(2026, 10, 18, 7), 120, WalStatus.uploadRejected, rejectionReason: WalUploadRejection.tooLarge),
      _wal(DateTime(2026, 10, 18, 6), 60, WalStatus.uploadRejected),
    ]);
    expect(find.text('Invalid recording date'), findsNothing);
    expect(find.text('Too large'), findsNothing);
    expect(find.text('Rejected by server'), findsNothing);
    expect(find.byKey(const Key('on_the_way_user_action')), findsNothing,
        reason: 'the refusal aggregate says no user action can help');
    await _expectNoActions(tester, sync, 3);
    // Support sees each refusal and its token.
    expect(find.text('Invalid recording date'), findsOneWidget);
    expect(find.textContaining('too_large'), findsOneWidget);
  });

  testWidgets('an exhausted transient failure is not a row and offers no action', (tester) async {
    final sync =
        await _pump(tester, [_wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.miss)..retryCount = walMaxAutoRetries]);
    expect(find.text('Failed — tap Retry'), findsNothing);
    await _expectNoActions(tester, sync, 1);
    expect(find.text('Failed — tap Retry'), findsOneWidget);
    expect(find.text('failed'), findsOneWidget);
  });

  testWidgets('a recording that cannot be retried offers no Delete here either', (tester) async {
    final sync = await _pump(tester, [_wal(DateTime(2026, 10, 18, 7), 60, WalStatus.outsideRecoveryWindow)]);
    await _expectNoActions(tester, sync, 1);
  });

  testWidgets('a recording made of several WALs is one support row with its whole length', (tester) async {
    // One 75-second-chunk recording the pendant handed over in three files:
    // 7:56, 7:57:15, 7:58:30, each exhausted its transient retry budget.
    final sync = await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 7, 58, 30), 75, WalStatus.miss)..retryCount = walMaxAutoRetries,
      _wal(DateTime(2026, 10, 18, 7, 57, 15), 75, WalStatus.miss)..retryCount = walMaxAutoRetries,
      _wal(DateTime(2026, 10, 18, 7, 56), 75, WalStatus.miss)..retryCount = walMaxAutoRetries,
    ]);
    await _expectNoActions(tester, sync, 3);
    expect(_row('7:56 AM · 3m 45s'), findsOneWidget, reason: 'the row names the whole recording\'s length');
  });

  testWidgets('a block with one member still uploading keeps that part on the page', (tester) async {
    final failed = _wal(DateTime(2026, 10, 18, 7, 58, 30), 75, WalStatus.miss)..retryCount = walMaxAutoRetries;
    final uploading = _wal(DateTime(2026, 10, 18, 7, 57, 15), 75, WalStatus.miss)..isSyncing = true;
    final sync = await _pump(tester, [failed, uploading]);
    expect(find.text('Uploading'), findsOneWidget, reason: 'the moving part still counts on Today');
    await _expectNoActions(tester, sync, 2);
  });

  testWidgets('an undated refusal also stays quiet and retained', (tester) async {
    final wal = _wal(DateTime(1985, 9, 5, 16, 17), 180, WalStatus.uploadRejected,
        rejectionReason: WalUploadRejection.invalidCaptureTime);
    final sync = await _pump(tester, [wal]);
    expect(find.text('Invalid recording date'), findsNothing);
    expect(find.text('No date'), findsNothing);
    await _expectNoActions(tester, sync, 1);
    expect(find.textContaining('1985'), findsNothing);
  });
}
