import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

class _Temp extends PathProviderPlatform {
  _Temp(this.path);
  final String path;
  @override
  Future<String> getTemporaryPath() async => path;
}

class _Recorder implements AnalyticsAdapter {
  final events = <(String, Map<String, Object>)>[];
  bool initialized = false;
  @override
  bool get isInitialized => initialized;
  @override
  Future<void> init() async => initialized = true;
  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}
  @override
  void alias({required String newUserId}) {}
  @override
  void track({required String eventName, Map<String, Object>? properties}) =>
      events.add((eventName, properties ?? const {}));
  @override
  void setInteractionContext({String? screenName, required String target}) {}
  @override
  void registerSuperProperties(Map<String, Object> properties) {}
  @override
  void enable() {}
  @override
  void disable() {}
  @override
  void reset() {}
}

ServerConversation _conversation({List<TranscriptSegment>? lines}) => ServerConversation(
      id: 'export-1',
      createdAt: DateTime(2026, 10, 22, 8, 31),
      startedAt: DateTime(2026, 10, 22, 8, 31),
      structured: Structured('Design review', 'Overview'),
      status: ConversationStatus.completed,
      transcriptSegments: lines ??
          [
            TranscriptSegment(
              id: 's1',
              text: 'Ship it on Friday.',
              speaker: 'SPEAKER_0',
              isUser: false,
              personId: null,
              start: 0,
              end: 4,
              translations: [],
            ),
          ],
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late Directory temp;
  late PathProviderPlatform previousPaths;
  late _Recorder analytics;
  late List<MethodCall> shares;
  const shareChannel = MethodChannel('dev.fluttercommunity.plus/share');

  setUp(() async {
    temp = Directory.systemTemp.createTempSync('export-transcript-');
    previousPaths = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Temp(temp.path);
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    analytics = _Recorder();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    shares = [];
    messenger.setMockMethodCallHandler(shareChannel, (call) async {
      shares.add(call);
      return 'dev.fluttercommunity.plus/share/success';
    });
  });

  tearDown(() {
    AnalyticsManager.resetForTesting();
    messenger.setMockMethodCallHandler(shareChannel, null);
    PathProviderPlatform.instance = previousPaths;
    temp.deleteSync(recursive: true);
  });

  Future<void> pumpPage(WidgetTester tester, ServerConversation item) async {
    // A phone-sized screen: on the default test surface the overflow menu runs off the bottom.
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.reset);
    final conversations = ConversationProvider(isSignedIn: () => false);
    final apps = AppProvider();
    final detail = ConversationDetailProvider();
    final folders = FolderProvider(foldersFetcher: () async => []);
    conversations.conversations = [item];
    conversations.conversationDetailsFetcherOverride = (id) async => item;
    detail.setProviders(apps, conversations);
    detail.setCachedConversation(item);
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
        ChangeNotifierProvider<AppProvider>.value(value: apps),
        ChangeNotifierProvider<FolderProvider>.value(value: folders),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: ConversationDetailPage(conversation: item),
      ),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
  }

  Future<void> exportFromMenu(WidgetTester tester) async {
    await tester.tap(find.byKey(const Key('conversation_more')));
    await tester.pumpAndSettle();
    expect(find.text('Export Transcript'), findsOneWidget);
    // The export does real file I/O, which only completes while real time runs.
    await tester.runAsync(() async {
      await tester.tap(find.text('Export Transcript'));
      for (var i = 0; i < 20; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 25));
        await tester.pump();
      }
    });
    await tester.pumpAndSettle();
  }

  testWidgets('Export Transcript writes the file, opens the share sheet and records the action', (tester) async {
    await pumpPage(tester, _conversation());
    await exportFromMenu(tester);

    final written = Directory('${temp.path}/transcript_exports').listSync().whereType<File>().toList();
    expect(written.map((f) => f.path.split('/').last), ['2026-10-22 0831 Design review.txt']);
    expect(await tester.runAsync(() => written.single.readAsString()), contains('Ship it on Friday.'));
    expect(shares, hasLength(1), reason: 'the share sheet carries the file');
    expect(shares.single.arguments.toString(), allOf(contains('Design review.txt'), contains('text/plain')));
    await tester.runAsync(() => AnalyticsManager.flushPending(force: true));
    final actions = analytics.events
        .where((e) => e.$1 == 'Conversation Action')
        .map((e) => {'action': e.$2['action'], 'surface': e.$2['surface']})
        .toList();
    expect(actions, [
      {'action': 'export_transcript', 'surface': 'overflow'},
    ]);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a failed export says so and offers Try Again, without opening the share sheet', (tester) async {
    // A file where the export folder's parent should be: nothing can be written there.
    final blocked = File('${temp.path}/blocked')..writeAsStringSync('');
    PathProviderPlatform.instance = _Temp(blocked.path);
    await pumpPage(tester, _conversation());
    await exportFromMenu(tester);

    expect(find.text('Export failed. Please try again.'), findsOneWidget);
    expect(find.text('Try Again'), findsOneWidget);
    expect(shares, isEmpty);

    // Once writing works again, Try Again completes the export.
    PathProviderPlatform.instance = _Temp(temp.path);
    await tester.runAsync(() async {
      await tester.tap(find.text('Try Again'));
      for (var i = 0; i < 20; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 25));
        await tester.pump();
      }
    });
    await tester.pumpAndSettle();
    expect(shares, hasLength(1));
    // Let the toast's hide animation (started by the Try Again tap) finish before the page goes.
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    // Its completion callback was scheduled in real time (the tap ran under runAsync); flush it.
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a conversation with no transcript offers nothing to export', (tester) async {
    await pumpPage(tester, _conversation(lines: const []));
    await tester.tap(find.byKey(const Key('conversation_more')));
    await tester.pumpAndSettle();

    expect(find.text('Export Transcript'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
}
