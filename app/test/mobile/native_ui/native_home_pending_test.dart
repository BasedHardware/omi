import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/capture/optimistic_processing.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart';

import 'native_test_host.dart';

final _l10n = lookupAppLocalizations(const Locale('en'));

class _InertRecordings extends ChangeNotifier implements LocalRecordingsProvider {
  @override
  List<LocalRecording> get recordings => const [];

  @override
  Future<void> refresh() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _InertDevice extends ChangeNotifier implements DeviceProvider {
  @override
  bool get havingNewFirmware => false;

  @override
  BtDevice? get pairedDevice => null;

  @override
  bool get isConnected => false;

  @override
  BtDevice? get connectedDevice => null;

  @override
  bool get isConnecting => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _InertCalls extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.idle;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// No recording is syncing or transcribing: the row's only other sources are processing
/// conversations and server-side pending work.
class _InertSync extends ChangeNotifier implements SyncProvider {
  @override
  SyncState get syncState => const SyncState();

  @override
  List<Wal> get allWals => const [];

  @override
  List<Wal> get displaySortedWals => const [];

  @override
  bool get isRateLimited => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<({List<DailySummary> items, bool ok})> _noRecaps() async => (items: const <DailySummary>[], ok: true);

/// A pending-work store answering from memory: [pending] is what the server reports as on its way.
PendingWorkStore _store({List<PendingWorkItem> pending = const []}) => PendingWorkStore(
      loadPending: () async => ApiSuccess(PendingWorkSnapshot(enabled: true, items: pending, attentionUnseenCount: 0)),
      loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
      retry: (_, {required idempotencyKey}) async => throw UnimplementedError(),
      retryAll: ({required idempotencyKey}) async => throw UnimplementedError(),
      markSeen: (_) async => const ApiSuccess<void>(null),
    );

/// The Home owners with no I/O behind them. They sit above the navigator so the On the Way page the
/// row opens finds them, as it does in the app.
Widget _app(ConversationProvider conversations, PendingWorkStore store) => MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
        ChangeNotifierProvider.value(value: conversations),
        ChangeNotifierProvider<LocalRecordingsProvider>(create: (_) => _InertRecordings()),
        ChangeNotifierProvider<SyncProvider>(create: (_) => _InertSync()),
        ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
        ChangeNotifierProvider(create: (_) => HomeProvider()),
        ChangeNotifierProvider<DeviceProvider>(create: (_) => _InertDevice()),
        ChangeNotifierProvider<PhoneCallProvider>(create: (_) => _InertCalls()),
        ChangeNotifierProvider(
            create: (_) => CaptureProvider(
                externalActions: const NoopCaptureExternalActions(),
                inProgressConversationLoader: () async {},
                localSegmentStore: LocalSegmentStore.disabled())),
        ChangeNotifierProvider(
            create: (_) => SpeakerTagPromptsProvider(
                fetchPrompts: () async => const ApiSuccess(GeneratedSpeakerTagPromptsResponse()))),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: IosNativeHome(requestInitialLoad: false, loadRecaps: _noRecaps, pendingWork: store),
        ),
      ),
    );

/// The chrome's pending row from the newest snapshot Swift received, or null when Home drew none.
Map? _pending(NativeTestHost host) {
  final updates = host.calls.where((call) => call.$2.method == 'update').toList();
  expect(updates, isNotEmpty, reason: 'Home publishes a snapshot once its view exists');
  final snapshot = updates.last.$2.arguments as Map;
  return (snapshot['chrome'] as Map)['pending'] as Map?;
}

List<String> _groupIds(NativeTestHost host) {
  final snapshot = host.calls.lastWhere((call) => call.$2.method == 'update').$2.arguments as Map;
  return [for (final group in snapshot['groups'] as List) (group as Map)['id'] as String];
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  // Home draws no processing cards of its own any more: a conversation still processing joins the one
  // pending row, and slow work never says it is taking longer.
  testWidgets('a processing conversation projects the pending row instead of a processing group', (tester) async {
    final host = NativeTestHost.install();
    final conversations = ConversationProvider(isSignedIn: () => true)
      ..addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    addTearDown(conversations.dispose);
    await tester.pumpWidget(_app(conversations, _store()));
    await NativeTestHost.settle(tester);

    expect(_pending(host), {'title': _l10n.homePendingTitle, 'subtitle': _l10n.processing});
    expect(_groupIds(host), isNot(contains('processing')));
  });

  testWidgets('nothing on the way projects no row, and the row clears when processing ends', (tester) async {
    final host = NativeTestHost.install();
    final conversations = ConversationProvider(isSignedIn: () => true);
    addTearDown(conversations.dispose);
    await tester.pumpWidget(_app(conversations, _store()));
    await NativeTestHost.settle(tester);
    expect(_pending(host), isNull);

    conversations.addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    await NativeTestHost.settle(tester);
    expect(_pending(host), isNotNull);

    conversations.removeProcessingConversation(OptimisticProcessingPlaceholder.id);
    await NativeTestHost.settle(tester);
    expect(_pending(host), isNull);
  });

  testWidgets('server work the phone did not start shows the row once the store has read it', (tester) async {
    final host = NativeTestHost.install();
    final conversations = ConversationProvider(isSignedIn: () => true);
    addTearDown(conversations.dispose);
    final store = _store(pending: const [
      PendingWorkItem(id: 'conv:1', kind: 'conversation', state: 'transcribing', conversationIds: ['1']),
    ]);
    await tester.pumpWidget(_app(conversations, store));
    await NativeTestHost.settle(tester);

    expect(store.pending, hasLength(1), reason: 'Home refreshes the store when it mounts');
    expect(_pending(host), {'title': _l10n.homePendingTitle, 'subtitle': _l10n.processing});
  });

  testWidgets('opening the row pushes the On the Way page', (tester) async {
    final host = NativeTestHost.install();
    final conversations = ConversationProvider(isSignedIn: () => true)
      ..addProcessingConversation(OptimisticProcessingPlaceholder.conversation());
    addTearDown(conversations.dispose);
    await tester.pumpWidget(_app(conversations, _store()));
    await NativeTestHost.settle(tester);

    // The handler awaits the pushed route, so the send only completes when On the Way pops.
    unawaited(host.sendFromNative(host.created.single, const MethodCall('openPending')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.byType(OnTheWayPage), findsOneWidget);
    expect(find.text(_l10n.onTheWayTitle), findsOneWidget);
  });
}
