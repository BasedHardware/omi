// Home's Offline Sync status card (ConversationProcessingCard): the pipeline
// state Home shows after a conversation ends — audio the server is turning
// into conversations, and audio waiting for a sync while auto-sync is off.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart' show BleAudioCodec;
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/widgets/conversation_processing_card.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';

import '../harness.dart';

/// A SyncProvider reporting one fixed offline-sync pipeline state.
class _SyncAuditProvider extends ChangeNotifier implements SyncProvider {
  _SyncAuditProvider({this.wals = const [], this.job = const (doneSeconds: 0, totalSeconds: 0, tracked: false)});

  final List<Wal> wals;
  final ({int doneSeconds, int totalSeconds, bool tracked}) job;

  @override
  SyncState get syncState => const SyncState();
  @override
  bool get isSyncing => false;
  @override
  List<Wal> get allWals => wals;
  @override
  List<Wal> get displaySortedWals => wals;
  @override
  List<Wal> get uploadedWals => wals.where((w) => w.status == WalStatus.uploaded).toList();
  @override
  bool get isRateLimited => false;
  @override
  ({int processed, int total}) get offlineServerProcessingCounts =>
      (processed: job.doneSeconds, total: job.totalSeconds);
  @override
  ({int doneSeconds, int totalSeconds, bool tracked}) get offlineServerProcessingSeconds => job;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Wal _wal(String id, int minutes, WalStatus status) => Wal(
      timerStart: 1000 + id.length,
      codec: BleAudioCodec.opus,
      seconds: minutes * 60,
      status: status,
      storage: WalStorage.disk,
      device: 'pendant',
    );

final offlineProcessingScenarios = <AuditScenario>[
  AuditScenario(
    id: 'home-offline-processing',
    title: 'Home: recordings turning into conversations',
    page: 'lib/pages/conversations/widgets/conversation_processing_card.dart (ConversationProcessingCard)',
    state: 'A 40m recording finished and uploaded, still processing on the server, next to a 15m one already '
        'done; Home shows the pipeline, not a stale timestamp',
    run: (a) async {
      final p = _SyncAuditProvider(
        wals: [_wal('processing', 40, WalStatus.uploaded), _wal('done', 15, WalStatus.synced)],
        job: (doneSeconds: 15 * 60, totalSeconds: 55 * 60, tracked: true),
      );
      await a.pump(
        const Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          ConversationProcessingCard(multiFileSync: true),
        ]),
        providers: [ChangeNotifierProvider<SyncProvider>.value(value: p)],
      );
      expect(find.text('Turning 55m into conversations'), findsOneWidget);
      expect(find.text('15m of 55m done · you can leave this screen'), findsOneWidget);
      await a.shot('The card Home shows while the server processes a recording');
    },
  ),
  AuditScenario(
    id: 'home-offline-processing-ready',
    title: 'Home: recordings waiting for a sync',
    page: 'lib/pages/conversations/widgets/conversation_processing_card.dart (ConversationProcessingCard)',
    state: 'A 45m and a 15m recording saved on the phone, waiting for their sync; the card offers the tap '
        'into Offline Sync',
    run: (a) async {
      final p = _SyncAuditProvider(
        wals: [_wal('ready-a', 45, WalStatus.miss), _wal('ready-b', 15, WalStatus.miss)],
      );
      await a.pump(
        const Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          ConversationProcessingCard(multiFileSync: true),
        ]),
        providers: [ChangeNotifierProvider<SyncProvider>.value(value: p)],
      );
      expect(find.text('1h ready to sync'), findsOneWidget);
      await a.shot('The card Home shows when a sync is waiting for the user');
    },
  ),
];
