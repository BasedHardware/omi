import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/capture_group.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

class _InertRecordings extends ChangeNotifier implements LocalRecordingsProvider {
  @override
  List<LocalRecording> get recordings => const [];

  @override
  Future<void> refresh() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Connectivity extends ChangeNotifier implements ConnectivityProvider {
  _Connectivity(this.isConnected);

  @override
  final bool isConnected;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

ServerConversation _conversation(String id, String title,
        {bool locked = false, bool starred = false, CaptureGroup? group, int hour = 10}) =>
    ServerConversation(
        id: id,
        createdAt: DateTime(2026, 10, 4, hour),
        startedAt: DateTime(2026, 10, 4, hour),
        structured: Structured(title, 'Overview'),
        isLocked: locked,
        starred: starred,
        captureGroup: group);

/// Answers each native presentation with [reply] and records what was presented.
List<Map> _answerPresentations(Map<String, Object?>? Function(Map arguments) reply) {
  final presented = <Map>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method != 'present') return null;
    final arguments = call.arguments as Map;
    presented.add(arguments);
    return reply(arguments);
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

String _presentedTitle(Map arguments) => (arguments['snapshot'] as Map)['title'] as String;

void main() {
  late ConversationProvider provider;
  late NativeTestHost host;
  var pageRequests = 0;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  Future<void> pumpLibrary(WidgetTester tester, List<ServerConversation> conversations,
      {bool connected = true,
      List<ServerConversation> processing = const [],
      Set<String> merging = const {},
      int pages = 0}) async {
    host = NativeTestHost.install();
    if (pages > 0) {
      // A full first page from the list owner leaves more to load; later pages are only counted.
      provider = ConversationProvider(
          isSignedIn: () => true, conversationListFetcher: () async => (items: [...conversations], ok: true))
        ..conversationPageFetcherOverride = () async {
          pageRequests++;
          return (items: <ServerConversation>[], ok: true, truncated: false);
        };
      await provider.fetchConversations();
    } else {
      provider = ConversationProvider(isSignedIn: () => false)
        ..conversations = [...conversations]
        ..processingConversations = [...processing]
        ..mergingConversationIds.addAll(merging)
        ..groupConversationsByDate();
    }
    addTearDown(provider.dispose);
    // Above the app, as in production, so root-navigator sheets reach the owners too.
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
          ChangeNotifierProvider<ConversationProvider>.value(value: provider),
          ChangeNotifierProvider<LocalRecordingsProvider>(create: (_) => _InertRecordings()),
          ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
          ChangeNotifierProvider<ConnectivityProvider>(create: (_) => _Connectivity(connected)),
          ChangeNotifierProvider(
              create: (_) => CaptureProvider(
                  externalActions: const NoopCaptureExternalActions(),
                  inProgressConversationLoader: () async {},
                  localSegmentStore: LocalSegmentStore.disabled())),
        ],
        child: const MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: [Locale('en')],
            home: Scaffold(body: ConversationsPage(requestInitialLoad: false, nativeLibrary: true)))));
    await NativeTestHost.settle(tester);
    await tester.pump(const Duration(milliseconds: 300));
  }

  IosNativeSurface surface(WidgetTester tester) => tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));

  NativeRow row(WidgetTester tester, String id) =>
      IosNativeSurface.debugDispatchRows(tester.state<State<IosNativeSurface>>(find.byType(IosNativeSurface)))
          .singleWhere((row) => row.id == id);

  Future<void> sendSelection(WidgetTester tester, List<String> ids) async {
    await host.sendFromNative(host.created.last, MethodCall('action', {'id': '_selection', 'value': ids}));
    await tester.pump();
  }

  final eligibleA = _conversation('a', 'Standup');
  final eligibleB = _conversation('b', 'Retro', starred: true, hour: 11);
  final locked = _conversation('locked', 'Secret plan', locked: true, hour: 12);

  testWidgets('the toolbar enters selection natively; the title counts and merge needs two', (tester) async {
    await pumpLibrary(tester, [eligibleA, eligibleB, locked]);
    expect(find.byType(UiKitView), findsOneWidget);
    expect(surface(tester).toolbar.map((row) => row.id), ['library_back', 'library_search', 'library_select']);

    await row(tester, 'library_select').action!(null);
    await tester.pump();
    expect(provider.isSelectionModeActive, isTrue);
    // No fallback while selecting: the same native surface stays mounted.
    expect(find.byType(UiKitView), findsOneWidget);
    expect(surface(tester).title, _l10n.selectedCount(0));
    expect(surface(tester).toolbar.map((row) => row.id), ['library_cancel']);
    expect(surface(tester).selection!.selectable, {'library_conversation_a', 'library_conversation_b'});
    expect(row(tester, 'library_conversation_locked').subtitle, _l10n.conversationCannotBeMerged);
    expect(surface(tester).bottomBar.map((row) => row.id),
        ['library_selected_count', 'library_move', 'library_delete', 'library_merge']);
    expect(row(tester, 'library_move').enabled, isFalse);

    await sendSelection(tester, ['library_conversation_a']);
    expect(surface(tester).title, _l10n.selectedCount(1));
    expect(surface(tester).selection!.selected, {'library_conversation_a'});
    expect(row(tester, 'library_move').enabled, isTrue);
    expect(row(tester, 'library_merge').enabled, isFalse);

    await sendSelection(tester, ['library_conversation_a', 'library_conversation_b']);
    expect(row(tester, 'library_merge').enabled, isTrue);
    expect(surface(tester).bottomBar.first.title, _l10n.selectedCount(2));

    await row(tester, 'library_cancel').action!(null);
    await tester.pump();
    expect(provider.isSelectionModeActive, isFalse);
    expect(surface(tester).title, _l10n.conversations);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the selection diff toggles each changed eligible id once and the last one exits', (tester) async {
    await pumpLibrary(tester, [eligibleA, eligibleB, locked]);
    provider.enterSelectionMode();
    await tester.pump();
    final toggles = <String>[];
    provider.addListener(() => toggles.add(provider.selectedConversationIds.join(',')));

    // Unknown or ineligible ids never reach the owner: the command is refused as a whole.
    await expectLater(
        host.sendFromNative(
            host.created.last,
            const MethodCall('action', {
              'id': '_selection',
              'value': ['library_conversation_locked']
            })),
        completes);
    expect(provider.selectedConversationIds, isEmpty);
    // The owner's diff ignores ids outside the current projection too.
    await surface(tester).selection!.action(['library_conversation_a', 'library_conversation_gone', 'unknown']);
    expect(provider.selectedConversationIds, {'a'});
    expect(toggles, ['a']);

    // Swapping the only selected row adds first, so selection mode never ends on the way.
    await sendSelection(tester, ['library_conversation_b']);
    expect(provider.selectedConversationIds, {'b'});
    expect(provider.isSelectionModeActive, isTrue);
    // Repeating the same set is idempotent.
    toggles.clear();
    await sendSelection(tester, ['library_conversation_b']);
    expect(toggles, isEmpty);

    await sendSelection(tester, []);
    expect(provider.isSelectionModeActive, isFalse);
    expect(surface(tester).selection, isNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('row menus follow the conversation state; swipe delete asks first', (tester) async {
    final grouped = _conversation('grouped', 'Design review',
        hour: 9,
        group: const CaptureGroup(id: 'event', primaryId: 'grouped', members: [
          CaptureGroupMember(id: 'grouped', source: 'desktop'),
          CaptureGroupMember(id: 'other', source: 'omi'),
        ]));
    final merging = _conversation('merging', 'Merging', hour: 8);
    await pumpLibrary(tester, [eligibleA, eligibleB, locked, grouped, merging], merging: {'merging'});

    expect(row(tester, 'library_conversation_a').kind, 'navigation');
    expect(row(tester, 'library_conversation_a').options.keys, ['open', 'star', 'move', 'share', 'select', 'delete']);
    expect(row(tester, 'library_conversation_a').options['star'], _l10n.starConversation);
    expect(row(tester, 'library_conversation_a').swipeTrailing, ['delete']);
    expect(row(tester, 'library_conversation_b').options['star'], _l10n.unstarConversation);
    expect(row(tester, 'library_conversation_locked').title, _l10n.conversations);
    expect(row(tester, 'library_conversation_locked').options.keys, ['open', 'delete']);
    expect(row(tester, 'library_conversation_grouped').options.keys,
        ['open', 'star', 'move', 'share', 'recordings', 'separate', 'select', 'delete']);
    expect(row(tester, 'library_conversation_grouped').options['separate'], _l10n.captureRecordingSeparate);
    final mergingRow = row(tester, 'library_conversation_merging');
    expect(mergingRow.subtitle, _l10n.mergingStatus);
    expect(mergingRow.options, isEmpty);
    expect(mergingRow.projection['enabled'], isFalse);
    // The mixed-state library must stay on the native view, not just project rows a fallback ignores.
    expect(find.byType(UiKitView), findsOneWidget);
    expect(host.created, isNotEmpty);

    final presented = _answerPresentations((_) => {'action': 'cancel', 'values': <String, Object?>{}});
    await host.sendFromNative(
        host.created.last, const MethodCall('action', {'id': 'library_conversation_a', 'value': 'delete'}));
    await tester.pump(const Duration(milliseconds: 100));
    expect(presented.map(_presentedTitle), [_l10n.deleteConversationTitle]);
    expect(provider.conversations.map((c) => c.id), contains('a'));

    // Select from the row menu enters selection with that row selected.
    await row(tester, 'library_conversation_a').action!('select');
    await tester.pump();
    expect(provider.isSelectionModeActive, isTrue);
    expect(provider.selectedConversationIds, {'a'});
    expect(tester.takeException(), isNull);
  });

  testWidgets('bottom actions run only after their confirmations; offline delete explains', (tester) async {
    await pumpLibrary(tester, [eligibleA, eligibleB], connected: false);
    provider.enterSelectionMode();
    provider.toggleConversationSelection('a');
    provider.toggleConversationSelection('b');
    await tester.pump();

    final presented = _answerPresentations((_) => {'action': 'cancel', 'values': <String, Object?>{}});
    await row(tester, 'library_delete').action!(null);
    await tester.pump();
    expect(presented.single['alert'], isTrue);
    expect(_presentedTitle(presented.single), _l10n.unableToDeleteConversation);
    expect(provider.isSelectionModeActive, isTrue);
    expect(provider.conversations, hasLength(2));

    // Cancelling the merge confirmation merges nothing and keeps the selection.
    await row(tester, 'library_merge').action!(null);
    await tester.pump();
    expect(_presentedTitle(presented.last), _l10n.mergeConversations);
    expect(provider.mergingConversationIds, isEmpty);
    expect(provider.selectedConversationIds, {'a', 'b'});
    expect(tester.takeException(), isNull);
  });

  testWidgets('a confirmed bulk delete leaves selection mode before deleting', (tester) async {
    await pumpLibrary(tester, [eligibleA, eligibleB]);
    provider.enterSelectionMode();
    provider.toggleConversationSelection('a');
    await tester.pump();
    final presented = _answerPresentations((_) => {'action': 'confirm', 'values': <String, Object?>{}});
    unawaited(Future.sync(() => row(tester, 'library_delete').action!(null)));
    await tester.pump();
    expect(_presentedTitle(presented.single), _l10n.deleteConversationsTitle(1));
    expect(provider.isSelectionModeActive, isFalse);
    expect(provider.conversations.map((c) => c.id), ['b']);
    // Undo stays offered until its toast closes.
    await tester.pump(const Duration(seconds: 6));
    await tester.pump(const Duration(seconds: 6));
    expect(tester.takeException(), isNull);
  });

  testWidgets('the processing row keeps its card with Try again; disposal ends selection', (tester) async {
    final processing = ServerConversation(
        id: 'processing',
        createdAt: DateTime(2026, 10, 4, 13),
        startedAt: DateTime(2026, 10, 4, 13),
        structured: Structured('', ''),
        status: ConversationStatus.processing);
    await pumpLibrary(tester, [eligibleA], processing: [processing]);
    // The sheet's future completes when it closes.
    unawaited(Future.sync(() => row(tester, 'library_processing_processing').action!(null)));
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.byType(ProcessingConversationWidget), findsOneWidget);
    Navigator.of(tester.element(find.byType(ProcessingConversationWidget))).pop();
    await tester.pump(const Duration(milliseconds: 600));

    provider.enterSelectionMode();
    provider.toggleConversationSelection('a');
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(provider.isSelectionModeActive, isFalse);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Show more pages through onVisible, also while selecting', (tester) async {
    pageRequests = 0;
    final page = [
      for (var i = 0; i < 50; i++)
        ServerConversation(
            id: 'p$i',
            createdAt: DateTime(2026, 10, 4, 8, i),
            startedAt: DateTime(2026, 10, 4, 8, i),
            finishedAt: DateTime(2026, 10, 4, 8, i, 50),
            structured: Structured('Talk $i', 'Overview')),
    ];
    await pumpLibrary(tester, page, pages: 1);
    expect(provider.hasMoreConversations, isTrue);
    provider.enterSelectionMode();
    await tester.pump();
    final more = row(tester, 'library_more');
    expect(more.onVisible, isNotNull);
    await more.onVisible!(null);
    await tester.pump();
    expect(pageRequests, 1);
    expect(provider.isSelectionModeActive, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the owner ignores ineligible ids; Select needs an eligible row; Move opens its sheet first',
      (tester) async {
    await pumpLibrary(tester, [locked]);
    expect(surface(tester).toolbar.map((row) => row.id), ['library_back', 'library_search']);
    await tester.pumpWidget(const SizedBox());

    await pumpLibrary(tester, [eligibleA, eligibleB, locked]);
    provider.enterSelectionMode();
    await tester.pump();
    await surface(tester).selection!.action(['library_conversation_a', 'library_conversation_locked']);
    await tester.pump();
    expect(provider.selectedConversationIds, {'a'});

    unawaited(Future.sync(() => row(tester, 'library_move').action!(null)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));
    expect(find.text(_l10n.moveConversationsTo(1)), findsOneWidget);
    // Nothing moves and the selection stays until a folder is chosen.
    expect(provider.isSelectionModeActive, isTrue);
    expect(eligibleA.folderId, isNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a retryable summary adds Retry to its row', (tester) async {
    final failed = ServerConversation(
        id: 'failed',
        createdAt: DateTime(2026, 10, 4, 7),
        startedAt: DateTime(2026, 10, 4, 7),
        structured: Structured('Interview', ''),
        summaryRetryable: true);
    await pumpLibrary(tester, [failed, eligibleA]);
    final retry = row(tester, 'library_conversation_failed');
    expect(retry.options['retry_summary'], _l10n.retry);
    expect(retry.subtitle, endsWith(_l10n.conversationSummaryFailed));
    expect(row(tester, 'library_conversation_a').options, isNot(contains('retry_summary')));
    expect(tester.takeException(), isNull);
  });
}
