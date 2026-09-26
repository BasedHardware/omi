import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_tasks_tab.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/memories/widgets/memory_delete_undo.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/platform/platform_manager.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('MemoriesPage undo toast and deletion delays are cancelled on dispose', (tester) async {
    late MemoriesProvider memories;
    await tester.pumpWidget(
      _l10nApp(
        MultiProvider(
          providers: [
            ChangeNotifierProvider(
              create: (_) {
                memories = MemoriesProvider(
                  fetchMemoriesRequest: ({limit = 100, offset = 0, thisDeviceOnly = false}) async =>
                      const GetMemoriesResult([], true),
                  deleteMemoryRequest: (_) async => true,
                );
                return memories;
              },
            ),
            ChangeNotifierProvider(create: (_) => HomeProvider()),
          ],
          child: const MemoriesPage(),
        ),
      ),
    );
    await tester.pump();

    // A delete from the page shows the shared Undo toast and holds the server delete back; the
    // pending toast and the provider's backstop timer must not outlive the page.
    deleteMemoryWithUndo(
      tester.element(find.byType(MemoriesPage)),
      memories,
      Memory(
        id: 'mem-timer',
        uid: 'uid',
        content: 'deleted memory',
        category: MemoryCategory.manual,
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
        visibility: MemoryVisibility.private,
      ),
    );
    await tester.pump();

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.byType(MemoriesPage), findsNothing);
  });

  testWidgets('ActionItemDetailWidget completion delay is cancelled on dispose', (tester) async {
    final structured = Structured('Sprint', 'Overview', emoji: '🧠');
    structured.actionItems = [ActionItem('Ship the timer fix')];
    // ConversationDetailProvider.conversationOrNull() validates the
    // conversation's local day against selectedDate, which defaults to the
    // clock at provider construction. Derive both from the same instant so
    // the day-key comparison holds in every timezone and at any wall-clock
    // time instead of only when the runner's calendar day matches UTC.
    final conversationDate = DateTime.now().subtract(const Duration(hours: 2));
    final conversation = ServerConversation(
      id: 'conv-timer',
      createdAt: conversationDate,
      structured: structured,
    );
    final conversations = _ImmediateConversationProvider();
    conversations.conversations = [conversation];
    final detail = ConversationDetailProvider();
    detail.conversationProvider = conversations;
    detail.setCachedConversation(conversation);
    detail.selectedDate = conversationLocalDayKey(conversation.createdAt);

    await tester.pumpWidget(
      _l10nApp(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
          ],
          child: Scaffold(
            body: ActionItemDetailWidget(actionItem: structured.actionItems.first, conversationId: conversation.id),
          ),
        ),
      ),
    );
    await tester.pump();

    // InkWell also hosts a GestureDetector; the completion toggle is the nested
    // checkbox, which is the last one under this widget.
    tester
        .widget<GestureDetector>(
          find.descendant(of: find.byType(ActionItemDetailWidget), matching: find.byType(GestureDetector)).last,
        )
        .onTap!();
    await tester.pump();

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.byType(ActionItemDetailWidget), findsNothing);
    conversations.dispose();
    detail.dispose();
  });

  testWidgets('ConnectDevicePage scan delay is not armed after unmount', (tester) async {
    _stubPluginChannels();
    final bluetoothReady = Completer<void>();
    _stubBleHostApi('getBluetoothState', () async {
      await bluetoothReady.future;
      return ['on'];
    });
    _stubBleHostApi('startScan', () async => <Object?>[]);
    _stubBleHostApi('stopScan', () async => <Object?>[]);

    await tester.runAsync(() async {
      try {
        await ServiceManager.init();
      } catch (_) {}
    });

    final onboarding = OnboardingProvider()..hasBluetoothPermission = true;
    final devices = DeviceProvider(
      bleDiagnosticsLoader: (_) async => throw StateError('fixture: BLE diagnostics unused'),
      findDeviceRunner: (_) async => false,
    );
    onboarding.setDeviceProvider(devices);

    await tester.pumpWidget(
      _l10nApp(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<OnboardingProvider>(create: (_) => onboarding),
            ChangeNotifierProvider<DeviceProvider>(create: (_) => devices),
          ],
          child: const ConnectDevicePage(),
        ),
      ),
    );
    await tester.pump();

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    bluetoothReady.complete();
    await tester.pump();
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.byType(ConnectDevicePage), findsNothing);
  });

  testWidgets('ConnectDevicePage dispose cancels an already-started DeviceProvider periodic', (tester) async {
    _stubPluginChannels();
    _stubBleHostApi('getBluetoothState', () async => ['on']);
    _stubBleHostApi('startScan', () async => <Object?>[]);
    _stubBleHostApi('stopScan', () async => <Object?>[]);

    await tester.runAsync(() async {
      try {
        await ServiceManager.init();
      } catch (_) {}
    });

    final onboarding = OnboardingProvider()..hasBluetoothPermission = true;
    final devices = DeviceProvider(
      bleDiagnosticsLoader: (_) async => throw StateError('fixture: BLE diagnostics unused'),
      findDeviceRunner: (_) async => false,
    );
    onboarding.setDeviceProvider(devices);

    await tester.pumpWidget(
      _l10nApp(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<OnboardingProvider>.value(value: onboarding),
            ChangeNotifierProvider<DeviceProvider>.value(value: devices),
          ],
          child: const ConnectDevicePage(),
        ),
      ),
    );
    await tester.pump();

    devices.startDiscoveryScanningForTesting();
    expect(devices.hasActiveDiscoveryTimer, isTrue);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();

    expect(devices.hasActiveDiscoveryTimer, isFalse);
    expect(tester.takeException(), isNull);
    expect(find.byType(ConnectDevicePage), findsNothing);
    devices.dispose();
    onboarding.dispose();
  });

  testWidgets('ConversationDetailPage delay cancel completes waiters', (tester) async {
    final structured = Structured('Sprint', 'Overview', emoji: '🧠');
    final conversation = ServerConversation(
      id: 'conv-delay-completer',
      createdAt: DateTime(2026, 9, 18, 9),
      structured: structured,
    );
    final conversations = _ImmediateConversationProvider();
    conversations.conversations = [conversation];
    final detail = ConversationDetailProvider();
    detail.conversationProvider = conversations;
    detail.setCachedConversation(conversation);

    await tester.pumpWidget(
      _l10nApp(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
            ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
            ChangeNotifierProvider(create: (_) => AppProvider()),
            ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => [])),
            ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
            ChangeNotifierProvider(create: (_) => PeopleProvider()),
            ChangeNotifierProvider(
              create: (_) => IntegrationProvider(
                fetchStatus: (_) async => null,
                saveStatus: (_, __) async => false,
                deleteStatus: (_) async => false,
                persistPref: (_, __) async {},
              ),
            ),
          ],
          child: ConversationDetailPage(conversation: conversation),
        ),
      ),
    );
    await tester.pump();

    final state = tester.state<ConversationDetailPageState>(find.byType(ConversationDetailPage));
    final waiter = state.ownedDelayForTesting(const Duration(seconds: 30));
    var completed = false;
    waiter.then((_) => completed = true);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();

    expect(completed, isTrue);
    expect(tester.takeException(), isNull);
    conversations.dispose();
    detail.dispose();
  });

  testWidgets('ChatPage 300ms and 800ms delays are cancelled on dispose', (tester) async {
    await tester.pumpWidget(
      _l10nApp(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<MessageProvider>(create: (_) => _SilentMessageProvider()),
            ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
            ChangeNotifierProvider(create: (_) => HomeProvider()),
            ChangeNotifierProvider(create: (_) => VoiceRecorderProvider()),
            ChangeNotifierProvider(create: (_) => AppProvider()),
            ChangeNotifierProvider(
              create: (_) => IntegrationProvider(
                fetchStatus: (_) async => null,
                saveStatus: (_, __) async => false,
                deleteStatus: (_) async => false,
                persistPref: (_, __) async {},
              ),
            ),
          ],
          child: const ChatPage(autoMessage: 'hello from a notification'),
        ),
      ),
    );
    await tester.pump();

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.byType(ChatPage), findsNothing);
  });
}

Widget _l10nApp(Widget home) {
  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: const [Locale('en')],
    home: home,
  );
}

class _ImmediateConversationProvider extends ConversationProvider {
  @override
  Future<void> updateGlobalActionItemState(
    ServerConversation conversation,
    String actionItemDescription,
    bool newState,
  ) async {}
}

class _SilentMessageProvider extends MessageProvider {
  @override
  Future<void> fetchChatApps() async {}

  @override
  Future refreshMessages({bool dropdownSelected = false}) async {}
}

void _stubPluginChannels() {
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const channels = [
    'flutter.baseflow.com/permissions/methods',
    'dev.fluttercommunity.plus/device_info',
    'plugins.flutter.io/shared_preferences',
  ];
  for (final name in channels) {
    messenger.setMockMethodCallHandler(MethodChannel(name), (call) async {
      switch (call.method) {
        case 'checkPermission':
        case 'checkServiceStatus':
        case 'requestPermissions':
          return 1;
        case 'getAll':
          return <String, Object>{};
        default:
          return null;
      }
    });
  }
}

void _stubBleHostApi(String methodName, Future<Object?> Function() reply) {
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMessageHandler('dev.flutter.pigeon.omi_pigeon.BleHostApi.$methodName', (ByteData? message) async {
    return BleHostApi.pigeonChannelCodec.encodeMessage(await reply());
  });
}
