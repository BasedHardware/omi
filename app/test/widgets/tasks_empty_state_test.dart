import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/conversation_api_contract.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/ui/ui.dart';

import '../support/typed_action_items_screen.dart';
import '../support/typed_conversation_screen.dart';

void main() {
  for (final brightness in Brightness.values) {
    testWidgets('empty Tasks keeps conversation guidance and aligns with Home in $brightness', (tester) async {
      final previousPalette = OmiColors.active;
      OmiColors.active = OmiColors.forBrightness(brightness);
      addTearDown(() => OmiColors.active = previousPalette);
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      var status = 200;
      final provider = composeTypedActionItemsProvider(ActionItemsApi(
        baseUrl: 'http://fixture.invalid/',
        send: (_) async => http.Response(status == 200 ? '{"action_items":[],"has_more":false}' : '{}', status),
      ));
      addTearDown(provider.dispose);
      final screen = await buildTypedActionItemsScreen(provider) as MaterialApp;
      await provider.ensureLoaded();
      await tester.pumpWidget(MaterialApp(
        theme: buildOmiTheme(brightness: brightness),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: screen.home,
      ));
      await tester.pumpAndSettle();

      final l10n = AppLocalizations.of(tester.element(find.byType(ActionItemsPage)));
      final title = find.text(l10n.noTasksYet);
      final hint = find.text(l10n.tasksEmptyStateMessage);
      final icon = find.byIcon(Icons.task_alt_rounded);
      final create = find.text(l10n.createActionItem);
      expect(provider.apiViewState.phase, ApiViewPhase.empty);
      expect(find.byKey(const ValueKey('omi.action_items.empty')), findsOneWidget);
      expect(title, findsOneWidget);
      expect(hint, findsOneWidget);
      expect(icon, findsOneWidget);
      expect(l10n.tasksEmptyStateMessage, 'Start a conversation to create a task.');
      expect(create, findsNothing);
      expect(find.byType(OmiButton), findsNothing);
      expect(find.byType(FloatingActionButton), findsNothing);
      expect(tester.widget<Text>(title).style!.color, OmiColors.textPrimary);
      expect(tester.widget<Text>(hint).style!.color, OmiColors.textSecondary);
      expect(IconTheme.of(tester.element(icon)).color, OmiColors.textTertiary);
      final emptyTitleRect = tester.getRect(title);
      final emptyIconRect = tester.getRect(icon);

      status = 503;
      await provider.forceRefreshActionItems();
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('omi.action_items.error')), findsOneWidget);
      expect(icon, findsNothing);
      expect(hint, findsNothing);
      expect(create, findsNothing);

      status = 200;
      await tester.tap(find.text(l10n.retry));
      await tester.pumpAndSettle();
      expect(provider.apiViewState.phase, ApiViewPhase.empty);
      expect(icon, findsOneWidget);
      expect(hint, findsOneWidget);
      expect(create, findsNothing);
      expect(tester.getRect(title), emptyTitleRect);

      tester.platformDispatcher.textScaleFactorTestValue = 2;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(tester.getRect(hint).bottom, lessThan(844));
      tester.platformDispatcher.clearTextScaleFactorTestValue();

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 1));

      final conversations = composeTypedConversationProvider(ConversationApi(
        baseUrl: 'http://fixture.invalid/',
        send: (_) async => http.Response('[]', 200),
      ));
      addTearDown(conversations.dispose);
      final home = await buildTypedConversationScreen(conversations) as MaterialApp;
      await conversations.forceRefreshConversations();
      await tester.pumpWidget(MaterialApp(
        theme: buildOmiTheme(brightness: brightness),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: home.home,
      ));
      await tester.pumpAndSettle();
      final homeTitleRect = tester.getRect(find.text(l10n.noConversationsYet));
      expect(emptyTitleRect.top, homeTitleRect.top);
      expect(emptyTitleRect.center.dx, homeTitleRect.center.dx);
      expect(emptyIconRect, tester.getRect(find.byIcon(Icons.forum_rounded)));

      tester.platformDispatcher.textScaleFactorTestValue = 2;
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(tester.getRect(find.text(l10n.noConversationsHeroMessage)).bottom, lessThan(844));
      tester.platformDispatcher.clearTextScaleFactorTestValue();

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 1));
    });
  }
}
