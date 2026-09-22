// Agent visual inspection lane: real production widgets, synthetic local I/O.
// See README.md. This is a capture tool, not native-device qualification.
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/pages/chat/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import '../journeys/support/hermetic_boot.dart';

class _LoopbackOnly extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..findProxy = (uri) {
        if (uri.host != '127.0.0.1') throw StateError('Visual audit blocks external request: ${uri.host}');
        return 'DIRECT';
      };
  }
}

final _frames = <Map<String, Object?>>[];
final _output = Directory(Platform.environment['OMI_AUDIT_OUTPUT']!);
const _surface = ValueKey('audit-surface');

Future<void> _fonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  final loader = FontLoader('Roboto');
  for (final weight in ['Regular', 'Medium', 'Bold']) {
    final bytes = File('${Platform.environment['OMI_AUDIT_FONTS']}/Roboto-$weight.ttf').readAsBytesSync();
    loader.addFont(Future.value(ByteData.sublistView(bytes)));
  }
  await loader.load();
}

Future<void> _pump(WidgetTester tester, Widget page, {List<SingleChildWidget> providers = const []}) async {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider(create: (_) => MessageProvider()),
      ChangeNotifierProvider(create: (_) => ActionItemsProvider()),
      ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
      ChangeNotifierProvider(create: (_) => AppProvider()),
      ChangeNotifierProvider(create: (_) => ConversationProvider(isSignedIn: () => true)),
      ChangeNotifierProvider(create: (_) => HomeProvider()),
      ChangeNotifierProvider(create: (_) => IntegrationProvider()),
      ChangeNotifierProvider(create: (_) => FolderProvider()),
      ChangeNotifierProvider(create: (_) => UsageProvider()),
      ChangeNotifierProvider(create: (_) => VoiceRecorderProvider()),
      ChangeNotifierProvider(create: (_) => MemoriesProvider()),
      ...providers,
    ],
    child: RepaintBoundary(
        key: _surface,
        child: MaterialApp(
          debugShowCheckedModeBanner: false,
          navigatorKey: globalNavigatorKey,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          // Matches main.dart's theme; Android font metrics (Roboto).
          theme: ThemeData(
            useMaterial3: false,
            colorScheme:
                const ColorScheme.dark(primary: Colors.black, secondary: Color(0xFF35343B), surface: Colors.black38),
            snackBarTheme: const SnackBarThemeData(
                backgroundColor: Color(0xFF1F1F25),
                contentTextStyle: TextStyle(fontSize: 16, color: Colors.white, fontWeight: FontWeight.w500)),
            textTheme: TextTheme(
                titleLarge: const TextStyle(fontSize: 18, color: Colors.white),
                titleMedium: const TextStyle(fontSize: 16, color: Colors.white),
                bodyMedium: const TextStyle(fontSize: 14, color: Colors.white),
                labelMedium: TextStyle(fontSize: 12, color: Colors.grey.shade200)),
            textSelectionTheme: const TextSelectionThemeData(
                cursorColor: Colors.white, selectionColor: Colors.white24, selectionHandleColor: Colors.white),
            cupertinoOverrideTheme: const CupertinoThemeData(primaryColor: Colors.white),
          ),
          home: page,
        )),
  ));
  await _settle(tester);
}

Future<void> _settle(WidgetTester tester) async {
  // Give loopback I/O a real event-loop turn, then finish finite animations.
  for (var i = 0; i < 6; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 80)));
    await tester.pump(const Duration(milliseconds: 200));
  }
}

Future<void> _capture(WidgetTester tester, String name, String action) async {
  await tester.pump();
  final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(_surface));
  await tester.runAsync(() async {
    final image = await boundary.toImage(pixelRatio: 2);
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    await File('${_output.path}/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    image.dispose();
  });
  final text = tester
      .widgetList<Text>(find.byType(Text))
      .map((w) => w.data ?? w.textSpan?.toPlainText())
      .whereType<String>()
      .toList();
  final targets = <Map<String, Object?>>[];
  for (final element
      in find.byWidgetPredicate((w) => w is InkWell || w is IconButton || w is GestureDetector).evaluate()) {
    final box = element.findRenderObject();
    if (box is RenderBox && box.hasSize) {
      targets.add({'type': element.widget.runtimeType.toString(), 'width': box.size.width, 'height': box.size.height});
    }
  }
  _frames.add({
    'file': '$name.png',
    'action': action,
    'text': text,
    'targets': targets,
    'captured_at': DateTime.now().toUtc().toIso8601String()
  });
  File('${_output.path}/frames.json').writeAsStringSync(const JsonEncoder.withIndent('  ').convert(_frames));
  expect(tester.takeException(), isNull, reason: 'Capture must not hide layout/runtime errors');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    HttpOverrides.global = _LoopbackOnly();
    await _fonts();
    _output.createSync(recursive: true);
  });
  tearDown(() {
    JourneyHermeticBoot.stop();
  });

  testWidgets('memory list, empty save, draft and persisted save', (tester) async {
    final server = await tester.runAsync(() => JourneyHermeticBoot.start());
    addTearDown(() => server!.stop());
    await _pump(tester, const MemoriesPage());
    await _capture(tester, '01-memories-empty', 'Open Memories with an empty synthetic account');
    await tester.tap(find.byType(FloatingActionButton));
    await _settle(tester);
    await _capture(tester, '02-memory-create', 'Tap the add floating action button');
    expect(tester.widget<ElevatedButton>(find.byKey(const ValueKey('memory_save_button'))).onPressed, isNull);
    await tester.tap(find.byKey(const ValueKey('memory_save_button')));
    await _settle(tester);
    await _capture(tester, '03-memory-empty-save', 'Tap Save Memory with no content');
    await tester.enterText(find.byKey(const ValueKey('memory_content_field')),
        'I prefer morning meetings and keep Fridays free for focused work.');
    await _settle(tester);
    await _capture(tester, '04-memory-draft', 'Enter a synthetic preference');
    await tester.tap(find.byKey(const ValueKey('memory_save_button')));
    await _settle(tester);
    await _capture(tester, '05-memory-saved', 'Save the preference through the local fixture backend');
    await tester.tap(find.text('I prefer morning meetings and keep Fridays free for focused work.'));
    await _settle(tester);
    await _capture(tester, '05b-memory-edit', 'Tap the saved card to open quick edit');
    globalNavigatorKey.currentState!.pop();
    await _settle(tester);
    await tester.enterText(find.byType(TextField).first, 'weekend');
    await _settle(tester);
    await _capture(tester, '05c-memory-no-results', 'Search for a term absent from the saved memory');
    expect(find.text('🔍 No memories found'), findsOneWidget);
    await tester.tap(find.byKey(const Key('memories_empty_action')));
    await _settle(tester);
    expect(find.text('I prefer morning meetings and keep Fridays free for focused work.'), findsOneWidget);
    final memories = tester.element(find.byType(MemoriesPage)).read<MemoriesProvider>();
    memories.clearCategoryFilter();
    memories.toggleCategoryFilter(MemoryCategory.system);
    await _settle(tester);
    await _capture(tester, '05d-memory-filter-empty', 'Filter out the saved manual memory');
    await tester.tap(find.byKey(const Key('memories_empty_action')));
    await _settle(tester);
    expect(find.text('I prefer morning meetings and keep Fridays free for focused work.'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 5));
  });

  testWidgets('task creation and date selection', (tester) async {
    final server = await tester.runAsync(() => JourneyHermeticBoot.start());
    addTearDown(() => server!.stop());
    await _pump(
        tester,
        Scaffold(
            body: Builder(
                builder: (context) => Center(
                        child: TextButton(
                      onPressed: () => showModalBottomSheet(
                          context: context,
                          isScrollControlled: true,
                          backgroundColor: Colors.transparent,
                          builder: (_) => const ActionItemFormSheet()),
                      child: const Text('Open task form'),
                    )))));
    await tester.tap(find.text('Open task form'));
    await _settle(tester);
    await _capture(tester, '06-task-create', 'Open the production task creation sheet (neutral host)');
    await tester.enterText(find.byType(TextField).first, 'Send the design notes to Alex');
    await _settle(tester);
    await _capture(tester, '07-task-draft', 'Enter a task description');
    await tester.tap(find.text('Add due date'));
    await _settle(tester);
    await _capture(tester, '07b-task-date-picker', 'Tap Add due date');
    await tester.tap(find.text('Done'));
    await _settle(tester);
    await _capture(tester, '07c-task-date-selected', 'Confirm the date and return to the draft');
    expect(find.text('29/4096'), findsOneWidget);
    await tester.tap(find.byKey(const Key('task_quick_date_1')));
    await _settle(tester);
    await _capture(tester, '07d-task-quick-date', 'Choose Tomorrow in one tap');
    // A non-retryable rejection reaches the form; transient 503s are retried by the HTTP client.
    server!.failNext('POST', '/v1/action-items', status: 400);
    await tester.tap(find.byKey(const Key('task_save_button')));
    await _settle(tester);
    expect(find.byType(ActionItemFormSheet), findsOneWidget);
    await _capture(tester, '07e-task-save-failed', 'Rejected save keeps the task draft available to retry');
    await tester.tap(find.byKey(const Key('task_save_button')));
    await _settle(tester);
    expect(server.actionItems.single['description'], 'Send the design notes to Alex');
    expect(find.byType(ActionItemFormSheet), findsNothing);
    await _capture(tester, '07f-task-saved', 'Create the task and confirm server success');
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 5));
  });

  testWidgets('conversation detail', (tester) async {
    final server = await tester.runAsync(() => JourneyHermeticBoot.start());
    addTearDown(() => server!.stop());
    final conversation = ServerConversation(
        id: 'audit-conversation',
        createdAt: DateTime.now(),
        structured: Structured('Design catch-up with Alex',
            'We agreed to simplify the first recording experience, make saved memories easier to find, and send the revised design notes on Friday.',
            emoji: '💬', category: 'work'));
    server!.conversations.add(conversation.toJson());
    final provider = ConversationProvider(isSignedIn: () => true);
    await tester.runAsync(() => provider.forceRefreshConversations());
    await _pump(tester, ConversationDetailPage(conversation: conversation), providers: [
      ChangeNotifierProvider<ConversationProvider>.value(value: provider),
      ChangeNotifierProvider(
          create: (_) => ConversationDetailProvider()..selectedDate = conversationLocalDayKey(conversation.createdAt)),
    ]);
    await _capture(tester, '08-conversation-summary', 'Open a synthetic conversation detail');
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 5));
    provider.dispose();
  });

  testWidgets('chat empty, composing and reply', (tester) async {
    final server = await tester.runAsync(() => JourneyHermeticBoot.start());
    addTearDown(() => server!.stop());
    server!.assistantReplyText =
        'You agreed to send Alex the revised design notes on Friday. Start with the recording flow and memory search.';
    await _pump(tester, const ChatPage());
    await _capture(tester, '09-chat-empty', 'Open Ask Omi with no saved personal data');
    expect(find.text('What can you do for me?'), findsOneWidget);
    expect(find.text('Summarize my recent activity'), findsNothing);
    await tester.tap(find.byKey(const Key('chat_starter_goal')));
    await _settle(tester);
    expect(
        tester.widget<TextField>(find.byKey(const ValueKey('omi.chat.input'))).controller!.text, 'Help me set a goal');
    expect(server.countOf('POST', '/v2/messages'), 0);
    await _capture(tester, '09b-chat-starter-selected', 'Select a starter; it fills the composer without sending');
    await tester.enterText(find.byKey(const ValueKey('omi.chat.input')), 'What did I agree to send Alex?');
    await _settle(tester);
    await _capture(tester, '10-chat-draft', 'Compose a question');
    await tester.tap(find.byKey(const ValueKey('omi.chat.send')));
    await _settle(tester);
    await _capture(tester, '11-chat-reply', 'Send and receive the deterministic local assistant reply');
    expect(server.countOf('POST', '/v2/messages'), 1);
    mockCommonPlatformChannels();
    final copyIcon = find.byWidgetPredicate((w) => w is FaIcon && w.icon == FontAwesomeIcons.copy.data);
    await tester.tap(copyIcon);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await _capture(tester, '11b-chat-copy', 'Tap Copy and inspect its confirmation');
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 5));
  });
  testWidgets('chat starters with saved memories', (tester) async {
    final server = await tester.runAsync(() => JourneyHermeticBoot.start());
    addTearDown(() => server!.stop());
    final memories = MemoriesProvider();
    await tester.runAsync(() => memories.createMemory('I prefer morning meetings.', MemoryVisibility.private));
    await _pump(tester, const ChatPage(), providers: [ChangeNotifierProvider<MemoriesProvider>.value(value: memories)]);
    expect(find.text('Summarize my recent activity'), findsOneWidget);
    expect(find.text('How can I improve?'), findsOneWidget);
    expect(find.text('What can you do for me?'), findsNothing);
    await _capture(tester, '09c-chat-existing-data', 'Open empty chat with a saved memory');
    await tester.tap(find.byKey(const Key('chat_starter_activity')));
    await _settle(tester);
    expect(tester.widget<TextField>(find.byKey(const ValueKey('omi.chat.input'))).controller!.text,
        'Summarize my recent activity');
    expect(server!.countOf('POST', '/v2/messages'), 0);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 5));
    memories.dispose();
  });

  testWidgets('record source picker', (tester) async {
    final server = await tester.runAsync(() => JourneyHermeticBoot.start());
    addTearDown(() => server!.stop());
    await _pump(
        tester,
        Scaffold(
            backgroundColor: Colors.black,
            body: Builder(
                builder: (context) => Center(
                        child: TextButton(
                      onPressed: () => showModalBottomSheet(
                          context: context,
                          backgroundColor: Colors.transparent,
                          builder: (_) => RecordOptionsSheet(onPickPhoneMic: () {}, onPickPhoneCall: () {})),
                      child: const Text('Open record options'),
                    )))));
    await tester.tap(find.text('Open record options'));
    await _settle(tester);
    await _capture(
        tester, '12-record-options', 'Open the production recording source sheet (neutral host; capture not started)');
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 5));
  });
}
