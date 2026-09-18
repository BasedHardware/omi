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
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/platform/platform_manager.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('MemoriesPage overlay and deletion delays are cancelled on dispose', (tester) async {
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

    final state = tester.state<MemoriesPageState>(find.byType(MemoriesPage));
    state.showDeleteNotification('deleted memory', null);
    memories.deleteMemory(
      Memory(
        id: 'mem-timer',
        uid: 'uid',
        content: 'deleted memory',
        category: MemoryCategory.manual,
        createdAt: DateTime(2026, 9, 18),
        updatedAt: DateTime(2026, 9, 18),
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
    final conversation = ServerConversation(
      id: 'conv-timer',
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
