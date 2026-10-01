import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/backend/http/conversation_api_contract.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/ui/ui.dart';

import '../support/typed_conversation_screen.dart';

void main() {
  for (final brightness in Brightness.values) {
    testWidgets('Home keeps its empty icon, hint and layout after loading in $brightness', (tester) async {
      final previousPalette = OmiColors.active;
      OmiColors.active = OmiColors.forBrightness(brightness);
      addTearDown(() => OmiColors.active = previousPalette);
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      var status = 200;
      final provider = composeTypedConversationProvider(ConversationApi(
        baseUrl: 'http://fixture.invalid/',
        send: (_) async => http.Response(status == 200 ? '[]' : '{}', status),
      ));
      addTearDown(provider.dispose);
      final screen = await buildTypedConversationScreen(provider) as MaterialApp;
      await tester.pumpWidget(MaterialApp(
        theme: buildOmiTheme(brightness: brightness),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: screen.home,
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      final page = find.byType(ConversationsPage);
      final l10n = AppLocalizations.of(tester.element(page));
      final title = find.text(l10n.noConversationsYet);
      final hint = find.text(l10n.noConversationsHeroMessage);
      final icon = find.byIcon(Icons.forum_rounded);
      expect(title, findsOneWidget);
      expect(hint, findsOneWidget);
      expect(icon, findsOneWidget);
      final initialTitleRect = tester.getRect(title);

      await provider.forceRefreshConversations();
      await tester.pump();
      expect(provider.apiViewState.phase, ApiViewPhase.empty);
      expect(find.byKey(const ValueKey('omi.conversations.empty')), findsOneWidget);
      expect(title, findsOneWidget);
      expect(hint, findsOneWidget);
      expect(icon, findsOneWidget);
      expect(tester.getRect(title), initialTitleRect);
      expect(tester.widget<Text>(title).style!.color, OmiColors.textPrimary);
      expect(tester.widget<Text>(hint).style!.color, OmiColors.textSecondary);
      expect(IconTheme.of(tester.element(icon)).color, OmiColors.textTertiary);

      // A later outage must still show an error, and retry must restore the full hero.
      status = 503;
      await provider.forceRefreshConversations();
      await tester.pump();
      expect(find.byKey(const ValueKey('omi.conversations.error')), findsOneWidget);
      expect(icon, findsNothing);
      expect(hint, findsNothing);
      status = 200;
      await tester.tap(find.text(l10n.retry));
      await tester.pump();
      expect(provider.apiViewState.phase, ApiViewPhase.empty);
      expect(icon, findsOneWidget);
      expect(hint, findsOneWidget);
      expect(tester.getRect(title), initialTitleRect);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 1));
    });
  }
}
