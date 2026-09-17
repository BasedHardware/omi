import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/chat/widgets/chat_followup_chip.dart';
import 'package:omi/pages/chat/widgets/jump_to_latest_button.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/empty_conversations.dart';
import 'package:omi/pages/conversations/widgets/folder_tabs.dart';
import 'package:omi/pages/conversations/widgets/search_widget.dart';
import 'package:omi/pages/home/home_content.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart';
import 'package:omi/widgets/header_circle_button.dart';

import '../support/local_day.dart';
import '../support/semantics_tree.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'has_first_conversation': true,
      'has_shown_review_prompt': true,
      'has_shown_review_for_conversation': true,
    });
    await SharedPreferencesUtil.init();
  });

  testWidgets('harness classifies named buttons, unnamed taps, and headers', (tester) async {
    final handle = tester.ensureSemantics();
    try {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Column(
              children: [
                Semantics(header: true, child: const Text('Section')),
                HeaderCircleButton(icon: const Icon(Icons.settings), semanticLabel: 'Settings', onTap: () {}),
                GestureDetector(onTap: () {}, child: const Icon(Icons.chevron_left)),
              ],
            ),
          ),
        ),
      );

      final dump = dumpSemanticsTree(tester);
      expect(dump.headers, isNotEmpty);
      expect(dump.interactive.where((node) => node.accessibleName == 'Settings'), isNotEmpty);
      expect(dump.unnamedInteractive, isNotEmpty, reason: 'the icon-only GestureDetector has no name');
    } finally {
      handle.dispose();
    }
  });

  testWidgets('harness treats Semantics.identifier as machine-only, not a spoken name', (tester) async {
    final handle = tester.ensureSemantics();
    try {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Column(
              children: [
                Semantics(
                  identifier: 'omi.settings.done',
                  label: 'Done',
                  button: true,
                  excludeSemantics: true,
                  child: GestureDetector(onTap: () {}, child: const Text('Done')),
                ),
                Semantics(
                  identifier: 'omi.devices.gear',
                  label: 'omi.devices.gear',
                  button: true,
                  excludeSemantics: true,
                  child: GestureDetector(onTap: () {}, child: const Icon(Icons.settings)),
                ),
              ],
            ),
          ),
        ),
      );

      final dump = dumpSemanticsTree(tester);
      final done = dump.interactive.firstWhere((node) => node.identifier == 'omi.settings.done');
      expect(done.accessibleName, 'Done');
      expect(done.isUnhelpful, isFalse, reason: 'identifier must not leak into the spoken name');

      final leaked = dump.interactive.firstWhere((node) => node.identifier == 'omi.devices.gear');
      expect(leaked.accessibleName, 'omi.devices.gear');
      expect(leaked.unhelpfulReason, 'omi-grammar');
    } finally {
      handle.dispose();
    }
  });

  testWidgets('inventory: home', (tester) async {
    _printReport(await _measureHome(tester));
  });

  testWidgets('inventory: conversations', (tester) async {
    _printReport(await _measureConversations(tester));
  });

  testWidgets('inventory: conversation_detail', (tester) async {
    _printReport(await _measureConversationDetail(tester));
  });

  testWidgets('inventory: memories', (tester) async {
    _printReport(await _measureMemories(tester));
  });

  testWidgets('inventory: tasks', (tester) async {
    _printReport(await _measureTasks(tester));
  });

  testWidgets('inventory: settings', (tester) async {
    _printReport(await _measureSettings(tester));
  });

  testWidgets('inventory: onboarding', (tester) async {
    _printReport(await _measureOnboarding(tester));
  });

  testWidgets('inventory: devices', (tester) async {
    _printReport(await _measureDevices(tester));
  });

  testWidgets('inventory: chat', (tester) async {
    _printReport(await _measureChat(tester));
  });
}

String _quote(String value) => '"${value.replaceAll('"', r'\"')}"';

void _printReport(SurfaceSemanticsReport report) {
  final buffer = StringBuffer(report.summary);
  if (report.dump != null) {
    for (final node in report.dump!.interactive) {
      final name = node.hasAccessibleName ? _quote(node.accessibleName) : 'UNNAMED';
      buffer.writeln('\n  interactive #${node.id} $name flags=${node.flags} actions=${node.actions}');
    }
    for (final node in report.dump!.unhelpfulInteractive) {
      buffer.writeln('\n  unhelpful #${node.id} ${node.unhelpfulReason} ${_quote(node.accessibleName)}');
    }
    for (final entry in report.dump!.duplicatedLabels.entries) {
      buffer.writeln('\n  duplicate "${entry.key}" x${entry.value.length}');
    }
  }
  debugPrint(buffer.toString());
}

Widget _app(Widget child, {Widget Function(Widget child)? wrap}) {
  return MaterialApp(
    key: UniqueKey(),
    theme: ThemeData.dark(),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: wrap == null ? child : wrap(child),
  );
}

Widget _withProviders(Widget child, List<InheritedProvider<dynamic>> providers) {
  return MultiProvider(providers: providers, child: child);
}

ServerConversation _conversation(String id, String title, DateTime createdAt) {
  return ServerConversation(
    id: id,
    createdAt: createdAt,
    structured: Structured(title, 'Overview', emoji: '🧠'),
  );
}

Future<SurfaceSemanticsReport> _tryMeasure(
  WidgetTester tester, {
  required String surface,
  required String pumpedWidget,
  required Widget app,
  List<String> notes = const [],
}) async {
  final handle = tester.ensureSemantics();
  try {
    await tester.pumpWidget(app);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    return SurfaceSemanticsReport(
      surface: surface,
      pumpedWidget: pumpedWidget,
      dump: dumpSemanticsTree(tester),
      notes: notes,
    );
  } catch (error) {
    return SurfaceSemanticsReport(
      surface: surface,
      pumpedWidget: pumpedWidget,
      failureReason: error.toString(),
      notes: notes,
    );
  } finally {
    handle.dispose();
  }
}

Future<SurfaceSemanticsReport> _measureHome(WidgetTester tester) async {
  final home = HomeProvider();
  addTearDown(home.dispose);
  final conversations = ConversationProvider(isSignedIn: () => false);
  addTearDown(conversations.dispose);
  final today = localCalendarDay(2026, 8, 12, 15);
  final newest = _conversation('newest', 'Newest', today);
  conversations.conversations = [newest];
  conversations.groupedConversations = {
    DateTime(today.year, today.month, today.day): [newest],
  };

  return _tryMeasure(
    tester,
    surface: 'home',
    pumpedWidget: 'BottomNavBar + HomeConversationsPreview',
    notes: [
      'HomePage / HomeContentPage not pumped: HomePage owns uncancelled Timers; HomeContentPage fetches daily summaries.',
      'Tabs are icon-only and already wrap Semantics(label) from l10n.',
    ],
    app: _app(
      Scaffold(
        body: CustomScrollView(slivers: [HomeConversationsPreview(conversationProvider: conversations)]),
        bottomNavigationBar: BottomNavBar(onTabTap: (_, __) {}),
      ),
      wrap: (child) => _withProviders(child, [
        ChangeNotifierProvider<HomeProvider>.value(value: home),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
      ]),
    ),
  );
}

Future<SurfaceSemanticsReport> _measureConversations(WidgetTester tester) async {
  final home = HomeProvider();
  addTearDown(home.dispose);
  final conversations = ConversationProvider(isSignedIn: () => false);
  addTearDown(conversations.dispose);
  final folders = FolderProvider(foldersFetcher: () async => []);
  addTearDown(folders.dispose);
  final today = localCalendarDay(2026, 8, 12, 15);
  final item = _conversation('c1', 'Standup notes', today.subtract(const Duration(days: 2)));
  conversations.conversations = [item];
  conversations.groupedConversations = {
    DateTime(item.createdAt.year, item.createdAt.month, item.createdAt.day): [item],
  };

  return _tryMeasure(
    tester,
    surface: 'conversations',
    pumpedWidget: 'SearchWidget + FolderTabs + ConversationListItem + EmptyConversationsWidget',
    notes: [
      'ConversationsPage not pumped: it reads CaptureProvider, LocalRecordingsProvider, and refreshes folders/goals on pull.',
    ],
    app: _app(
      Scaffold(
        body: ListView(
          children: [
            const SearchWidget(),
            FolderTabs(
              folders: const [],
              selectedFolderId: null,
              onFolderSelected: (_) {},
              showStarredOnly: false,
              onStarredToggle: () {},
              showDailySummaries: false,
              onDailySummariesToggle: () {},
              hasDailySummaries: false,
            ),
            ConversationListItem(conversation: item, date: item.createdAt, conversationIdx: 0),
            const EmptyConversationsWidget(),
          ],
        ),
      ),
      wrap: (child) => _withProviders(child, [
        ChangeNotifierProvider<HomeProvider>.value(value: home),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
        ChangeNotifierProvider<FolderProvider>.value(value: folders),
      ]),
    ),
  );
}

Future<SurfaceSemanticsReport> _measureConversationDetail(WidgetTester tester) async {
  final conversations = ConversationProvider(isSignedIn: () => false);
  addTearDown(conversations.dispose);
  final apps = AppProvider();
  addTearDown(apps.dispose);
  final detail = ConversationDetailProvider();
  addTearDown(detail.dispose);
  final today = localCalendarDay(2026, 8, 12, 15);
  final item = _conversation('detail-1', 'Weekly recap', today.subtract(const Duration(days: 3)));
  conversations.conversations = [item];
  conversations.groupedConversations = {
    DateTime(item.createdAt.year, item.createdAt.month, item.createdAt.day): [item],
  };
  conversations.conversationDetailsFetcherOverride = (id) async => item;
  final folders = FolderProvider(foldersFetcher: () async => []);
  addTearDown(folders.dispose);
  detail.setProviders(apps, conversations);
  detail.setCachedConversation(item);
  detail.selectedDate = conversationLocalDayKey(item.createdAt);

  final page = await _tryMeasure(
    tester,
    surface: 'conversation_detail',
    pumpedWidget: 'ConversationDetailPage',
    notes: [
      'Back IconButton has no tooltip and no Semantics.label.',
      'Ask IconButton tooltip is l10n askAboutThisConversation.',
    ],
    app: _app(
      ConversationDetailPage(conversation: item),
      wrap: (child) => _withProviders(child, [
        ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
        ChangeNotifierProvider<AppProvider>.value(value: apps),
        ChangeNotifierProvider<FolderProvider>.value(value: folders),
      ]),
    ),
  );
  if (page.pumped) return page;

  return _tryMeasure(
    tester,
    surface: 'conversation_detail',
    pumpedWidget: 'ConversationBottomBar (detail mode); ConversationDetailPage failed: ${page.failureReason}',
    notes: [
      'Full ConversationDetailPage did not pump. Bottom bar is the production tab strip on that surface.',
      'AppBar Back (no tooltip) lives in conversation_detail/page.dart and was not in this slice.',
    ],
    app: _app(
      Scaffold(
        body: ConversationBottomBar(
          mode: ConversationBottomBarMode.detail,
          selectedTab: ConversationTab.summary,
          onTabSelected: (_) {},
          onStopPressed: () {},
        ),
      ),
      wrap: (child) => _withProviders(child, [ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail)]),
    ),
  );
}

Future<SurfaceSemanticsReport> _measureMemories(WidgetTester tester) async {
  final home = HomeProvider();
  addTearDown(home.dispose);
  const empty = GetMemoriesResult([], true);
  final memories = MemoriesProvider(
    fetchMemoriesRequest: ({limit = 100, offset = 0, thisDeviceOnly = false}) async => empty,
  );
  addTearDown(memories.dispose);

  return _tryMeasure(
    tester,
    surface: 'memories',
    pumpedWidget: 'MemoriesPage (empty fetch)',
    notes: [
      'Graph and management header buttons are ElevatedButton wrapping FaIcon with no semanticLabel.',
      'Empty-state retry lives in MemoriesLoadError; this pump is the loaded-empty page after init().',
    ],
    app: _app(
      const MemoriesPage(),
      wrap: (child) => _withProviders(child, [
        ChangeNotifierProvider<HomeProvider>.value(value: home),
        ChangeNotifierProvider<MemoriesProvider>.value(value: memories),
      ]),
    ),
  );
}

Future<SurfaceSemanticsReport> _measureTasks(WidgetTester tester) async {
  final items = ActionItemsProvider(
    getActionItems: (
            {limit = 50, offset = 0, completed, conversationId, startDate, endDate, dueStartDate, dueEndDate}) async =>
        const ActionItemsResponse(actionItems: [], hasMore: false),
  );
  addTearDown(items.dispose);
  final goals = GoalsProvider();
  addTearDown(goals.dispose);
  final integrations = _StubTaskIntegrationProvider();
  addTearDown(integrations.dispose);

  return _tryMeasure(
    tester,
    surface: 'tasks',
    pumpedWidget: 'ActionItemsPage (empty list)',
    notes: [
      'HeaderCircleButton on the goals row uses l10n addGoal when goals exist; empty list shows the empty-state pill.',
    ],
    app: _app(
      const ActionItemsPage(),
      wrap: (child) => _withProviders(child, [
        ChangeNotifierProvider<ActionItemsProvider>.value(value: items),
        ChangeNotifierProvider<GoalsProvider>.value(value: goals),
        ChangeNotifierProvider<TaskIntegrationProvider>.value(value: integrations),
      ]),
    ),
  );
}

Future<SurfaceSemanticsReport> _measureSettings(WidgetTester tester) async {
  final usage = _StubUsageProvider();
  addTearDown(usage.dispose);
  final device = _StubDeviceProvider();
  addTearDown(device.dispose);

  return _tryMeasure(
    tester,
    surface: 'settings',
    pumpedWidget: 'SettingsDrawer',
    notes: [
      'Rows are GestureDetector wrapping title Text; search is Icon-only GestureDetector with no tooltip.',
      'Done has visible text. Device settings row hides when disconnected.',
    ],
    app: _app(
      const Scaffold(body: SettingsDrawer()),
      wrap: (child) => _withProviders(child, [
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
      ]),
    ),
  );
}

Future<SurfaceSemanticsReport> _measureOnboarding(WidgetTester tester) async {
  final auth = _AuthForBaseline();
  addTearDown(auth.dispose);

  return _tryMeasure(
    tester,
    surface: 'onboarding',
    pumpedWidget: 'AuthComponent',
    notes: [
      'Host is not iOS/Android, so Sign in with Apple is not built (Platform.isIOS || Platform.isAndroid).',
      'Google button has visible l10n text. Privacy/terms are RichText tap recognizers.',
    ],
    app: _app(
      Scaffold(body: AuthComponent(onSignIn: () {})),
      wrap: (child) => _withProviders(child, [ChangeNotifierProvider<AuthenticationProvider>.value(value: auth)]),
    ),
  );
}

Future<SurfaceSemanticsReport> _measureDevices(WidgetTester tester) async {
  final device = _StubDeviceProvider(connected: true);
  addTearDown(device.dispose);

  return _tryMeasure(
    tester,
    surface: 'devices',
    pumpedWidget: 'DeviceSettings',
    notes: [
      'ConnectDevicePage not pumped: FindDevicesPage.scanDevices requires ServiceManager.instance.',
      'DeviceSettings is the production devices settings surface and is reachable hermetically.',
      'Connect chrome (back chevron, gear IconButton without tooltip, store TextButton, guide GestureDetector) lives on ConnectDevicePage.',
    ],
    app: _app(
      const DeviceSettings(),
      wrap: (child) => _withProviders(child, [ChangeNotifierProvider<DeviceProvider>.value(value: device)]),
    ),
  );
}

Future<SurfaceSemanticsReport> _measureChat(WidgetTester tester) async {
  return _tryMeasure(
    tester,
    surface: 'chat',
    pumpedWidget: 'ChatJumpToLatestButton + ChatFollowUpChip',
    notes: [
      'ChatPage not pumped: architect B1 teardown on #14315. These two widgets already set Semantics.label separately from Key.',
    ],
    app: _app(
      Scaffold(
        body: Column(
          children: [
            ChatJumpToLatestButton(label: 'Latest', onTap: () {}),
            ChatFollowUpChip(question: 'What was decided?', onSend: (_) {}),
          ],
        ),
      ),
    ),
  );
}

class _AuthForBaseline extends AuthenticationProvider {
  _AuthForBaseline() : super(initializeListeners: false);

  @override
  bool get isLocalDevProfile => false;
}

class _StubUsageProvider extends ChangeNotifier implements UsageProvider {
  @override
  UserSubscriptionResponse? get subscription => null;

  @override
  bool get showSubscriptionUI => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubTaskIntegrationProvider extends ChangeNotifier implements TaskIntegrationProvider {
  @override
  bool get hasLoaded => true;

  @override
  bool get isLoading => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _StubDeviceProvider({this.connected = false});

  final bool connected;

  @override
  bool get isConnected => connected;

  @override
  BtDevice? get connectedDevice => null;

  @override
  BtDevice? get pairedDevice => null;

  @override
  Future<void> getDeviceInfo() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
