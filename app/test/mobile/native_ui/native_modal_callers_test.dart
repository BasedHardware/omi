import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/widgets/detail_search_bar.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart' show ConversationTab;

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

/// The native detail page asks for presentations in order; [replies] answers each 'present' call.
/// A reply that is a [PlatformException] is thrown, as the Swift presenter's refusal would be.
List<Map> _answerPresentations(List<Object? Function(Map snapshot)> replies) {
  final presented = <Map>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method != 'present') return null;
    final snapshot = (call.arguments as Map)['snapshot'] as Map;
    presented.add(snapshot);
    final reply = replies[presented.length - 1](snapshot);
    if (reply is PlatformException) throw reply;
    return reply;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

final _refused = PlatformException(code: 'invalid_native_presentation');

/// Chooses the More menu entry titled [title].
Object? Function(Map) _choose(String title) => (snapshot) => {
      'action': (snapshot['toolbar'] as List).cast<Map>().firstWhere((row) => row['title'] == title)['id'],
      'values': <String, Object?>{},
    };

void main() {
  late ConversationDetailProvider detail;

  setUp(() async {
    SharedPreferences.setMockInitialValues({'has_first_conversation': true});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  Future<void> pumpNativeDetail(WidgetTester tester) async {
    NativeTestHost.install();
    final conversation = ServerConversation(
        id: 'native-detail',
        createdAt: DateTime.utc(2026, 10, 4, 10),
        status: ConversationStatus.completed,
        structured: Structured('Sprint planning', 'We agreed to ship the native screens.'));
    final conversations = ConversationProvider(isSignedIn: () => false)
      ..conversations = [conversation]
      ..conversationDetailsFetcherOverride = (_) async => conversation;
    final apps = AppProvider();
    detail = ConversationDetailProvider()..setProviders(apps, conversations);
    addTearDown(() {
      detail.dispose();
      conversations.dispose();
      apps.dispose();
    });
    await tester.pumpWidget(MultiProvider(
        providers: [
          ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
          ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
          ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
          ChangeNotifierProvider<AppProvider>.value(value: apps),
          ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => [])),
          ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
          ChangeNotifierProvider(create: (_) => PeopleProvider()),
          ChangeNotifierProvider(
              create: (_) => IntegrationProvider(
                  fetchStatus: (_) async => null,
                  saveStatus: (_, __) async => false,
                  deleteStatus: (_) async => false,
                  persistPref: (_, __) async {})),
        ],
        child: MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: ConversationDetailPage(conversation: conversation, initialTab: ConversationTab.summary))));
    await NativeTestHost.settle(tester);
    await tester.pump(const Duration(milliseconds: 300));
    await NativeTestHost.settle(tester);
    expect(find.byType(UiKitView), findsOneWidget, reason: 'The page starts native');
    expect(find.byKey(const Key('conversation_more')), findsNothing);
  }

  NativeRow row(WidgetTester tester, String id) {
    final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
    return [...surface.toolbar, ...surface.sections.expand((section) => section.rows)]
        .singleWhere((row) => row.id == id);
  }

  Future<void> settle(WidgetTester tester) async {
    await NativeTestHost.settle(tester);
    await tester.pump(const Duration(seconds: 1));
  }

  void expectClassicPage() {
    expect(find.byType(UiKitView), findsNothing);
    expect(find.byKey(const Key('conversation_more')), findsOneWidget);
  }

  testWidgets('a cancelled native menu keeps the native page', (tester) async {
    await pumpNativeDetail(tester);
    final presented = _answerPresentations([
      (_) => {'action': 'cancel', 'values': <String, Object?>{}}
    ]);
    await row(tester, 'detail_more').action!(null);
    await settle(tester);
    expect(presented.single['title'], _l10n.moreOptions);
    expect(find.byType(UiKitView), findsOneWidget);
    expect(find.byKey(const Key('conversation_more')), findsNothing);
  });

  testWidgets('an unavailable native menu restores the classic page and opens its menu', (tester) async {
    await pumpNativeDetail(tester);
    _answerPresentations([(_) => _refused]);
    await row(tester, 'detail_more').action!(null);
    await settle(tester);
    expectClassicPage();
    expect(find.text(_l10n.renameConversation), findsOneWidget, reason: 'The classic More menu is open');
    expect(find.text(_l10n.moveToFolder), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an unavailable rename editor hands the rename to the classic title field', (tester) async {
    await pumpNativeDetail(tester);
    final presented = _answerPresentations([_choose(_l10n.renameConversation), (_) => _refused]);
    await row(tester, 'detail_more').action!(null);
    await settle(tester);
    expect(presented.map((snapshot) => snapshot['title']), [_l10n.moreOptions, _l10n.renameConversation]);
    expectClassicPage();
    expect(detail.titleFocusNode!.hasFocus, isTrue);
    expect(detail.titleController!.selection, const TextSelection(baseOffset: 0, extentOffset: 15));
    expect(tester.takeException(), isNull);
  });

  testWidgets('an unavailable search editor opens the classic search field', (tester) async {
    await pumpNativeDetail(tester);
    _answerPresentations([_choose(_l10n.search), (_) => _refused]);
    await row(tester, 'detail_more').action!(null);
    await settle(tester);
    expectClassicPage();
    final search = find.descendant(of: find.byType(DetailSearchBar), matching: find.byType(TextField));
    expect(search, findsOneWidget);
    expect(tester.widget<TextField>(search).focusNode!.hasFocus, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an unavailable summary editor hands the edit to the classic in-place editor', (tester) async {
    await pumpNativeDetail(tester);
    final presented = _answerPresentations([(_) => _refused]);
    await row(tester, 'detail_summary_edit').action!(null);
    await settle(tester);
    expect(presented.single['title'], _l10n.summary);
    expectClassicPage();
    final editor = find.byWidgetPredicate(
        (widget) => widget is TextField && widget.controller?.text == 'We agreed to ship the native screens.');
    expect(editor, findsOneWidget, reason: 'The classic summary editor is open on the same selection');
    expect(tester.widget<TextField>(editor).focusNode!.hasFocus, isTrue);
    expect(find.text(_l10n.save), findsOneWidget);
    expect(detail.conversation.structured.overview, 'We agreed to ship the native screens.');

    // The request lasted one frame: later rebuilds do not reopen a closed editor.
    await tester.tap(find.text(_l10n.cancel));
    await settle(tester);
    expect(editor, findsNothing);
    detail.notifyListeners();
    await settle(tester);
    expect(editor, findsNothing);
    expect(tester.takeException(), isNull);
  });
}
