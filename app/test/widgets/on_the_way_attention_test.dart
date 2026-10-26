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

/// On the Way's rows that need attention: every row names its length and the
/// short reason it was refused, opens the same Sync Details, and offers the
/// Offline Sync page's own Retry and Delete actions.

class _FakeSync extends ChangeNotifier implements SyncProvider {
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

void main() {
  setUp(OnTheWayPage.resetFolds);

  testWidgets('a refused row names its length and which refusal it was', (tester) async {
    await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.uploadRejected,
          rejectionReason: WalUploadRejection.invalidCaptureTime),
      _wal(DateTime(2026, 10, 18, 7), 2 * 60, WalStatus.uploadRejected, rejectionReason: WalUploadRejection.tooLarge),
      _wal(DateTime(2026, 10, 18, 6), 60, WalStatus.uploadRejected),
    ]);

    expect(find.text('Invalid recording date'), findsOneWidget);
    expect(find.text('Too large'), findsOneWidget);
    expect(find.text('Rejected by server'), findsOneWidget,
        reason: 'a refusal without a stored token still names the server');
    expect(_row('8:00 AM · 4m'), findsOneWidget);
    expect(_row('2m'), findsNothing, reason: 'dated rows keep the time · length line');
  });

  testWidgets('a refused row retries and deletes with the Sync Details actions', (tester) async {
    final wal = _wal(DateTime(2026, 10, 18, 8), 4 * 60, WalStatus.uploadRejected,
        rejectionReason: WalUploadRejection.invalidCaptureTime);
    final sync = await _pump(tester, [wal]);

    await tester.tap(find.text('Try Again'));
    await tester.pump();
    expect(sync.retried, [wal]);

    await tester.tap(find.text('Delete'));
    await tester.pump(const Duration(milliseconds: 400));
    // The confirmation the Offline Sync page's Delete uses.
    await tester.tap(find.text('Delete').last);
    await tester.pump(const Duration(milliseconds: 400));
    expect(sync.deleted, [wal]);
  });

  testWidgets('a too-large row offers Delete only: a retry cannot change the bytes', (tester) async {
    final sync = await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 7), 2 * 60, WalStatus.uploadRejected, rejectionReason: WalUploadRejection.tooLarge),
    ]);

    expect(find.text('Too large'), findsOneWidget);
    expect(find.text('Try Again'), findsNothing, reason: 'the same bytes are the same size');
    expect(find.text('Delete'), findsOneWidget);
    expect(sync.retried, isEmpty);
  });

  testWidgets('a row that cannot be retried offers only Delete', (tester) async {
    final sync = await _pump(tester, [
      _wal(DateTime(2026, 10, 18, 7), 60, WalStatus.outsideRecoveryWindow),
    ]);

    expect(find.text('Try Again'), findsNothing);
    expect(find.text('Delete'), findsOneWidget);
    expect(sync.retried, isEmpty);
  });

  testWidgets('a recording made of several WALs acts as one row over every member', (tester) async {
    // One 75-second-chunk recording the pendant handed over in three files:
    // 7:56, 7:57:15, 7:58:30, each refused for its claimed date.
    final wals = [
      _wal(DateTime(2026, 10, 18, 7, 58, 30), 75, WalStatus.uploadRejected,
          rejectionReason: WalUploadRejection.invalidCaptureTime),
      _wal(DateTime(2026, 10, 18, 7, 57, 15), 75, WalStatus.uploadRejected,
          rejectionReason: WalUploadRejection.invalidCaptureTime),
      _wal(DateTime(2026, 10, 18, 7, 56), 75, WalStatus.uploadRejected,
          rejectionReason: WalUploadRejection.invalidCaptureTime),
    ];
    final sync = await _pump(tester, wals);

    expect(find.text('Invalid recording date'), findsOneWidget, reason: 'the block reads as one recording');
    expect(_row('7:56 AM · 3m 45s'), findsOneWidget, reason: 'the row names the whole recording\'s length');

    await tester.tap(find.text('Try Again'));
    await tester.pump();
    expect(sync.retried, containsAll(wals), reason: 'Retry goes over every member WAL');
    expect(sync.retried, hasLength(3));

    await tester.tap(find.text('Delete'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Delete').last); // one confirmation for the whole block
    await tester.pump(const Duration(milliseconds: 400));
    expect(sync.deleted, containsAll(wals), reason: 'Delete removes every member WAL');
  });

  testWidgets('an undated refused row shows its length, reason and actions like dated ones', (tester) async {
    // A pendant clock that was never set: no plausible time, but the length
    // and the refusal still read, and the row still acts.
    final wal = _wal(DateTime(1985, 9, 5, 16, 17), 3 * 60, WalStatus.uploadRejected,
        rejectionReason: WalUploadRejection.invalidCaptureTime);
    final sync = await _pump(tester, [wal]);

    expect(find.text('3m'), findsOneWidget, reason: 'undated rows show the length on the first line');
    expect(find.text('Invalid recording date'), findsOneWidget);
    expect(find.text('Try Again'), findsOneWidget);
    expect(find.text('Delete'), findsOneWidget);

    await tester.tap(find.text('Try Again'));
    await tester.pump();
    expect(sync.retried, [wal]);
  });

  testWidgets('a block Delete never removes a member that is still uploading', (tester) async {
    // One recording, two members: one refused for its claimed date, one
    // mid-upload. The block reads as refused — its worst member — but the
    // Delete must take only the idle refused member; audio on its way is
    // never destroyed under a refusal label that belongs to another member.
    final refused = _wal(DateTime(2026, 10, 18, 7, 58, 30), 75, WalStatus.uploadRejected,
        rejectionReason: WalUploadRejection.invalidCaptureTime);
    final uploading = _wal(DateTime(2026, 10, 18, 7, 57, 15), 75, WalStatus.miss)..isSyncing = true;
    final sync = await _pump(tester, [refused, uploading]);

    expect(find.text('Invalid recording date'), findsOneWidget, reason: 'the block reads as one refused recording');
    expect(find.text('Delete'), findsOneWidget);

    await tester.tap(find.text('Delete'));
    await tester.pump(const Duration(milliseconds: 400));
    await tester.tap(find.text('Delete').last); // one confirmation for the whole block
    await tester.pump(const Duration(milliseconds: 400));

    expect(sync.deleted, [refused], reason: 'only the idle refused member is deleted');
    expect(sync.deleted, isNot(contains(uploading)), reason: 'the uploading member is kept');
    expect(find.text('Some parts are still uploading and were kept'), findsOneWidget,
        reason: 'the row says what was skipped, in the app\'s toast style');
  });
}
