import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/action_items_api_contract.dart';
import 'package:omi/backend/http/api_presentation.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart';
import 'package:omi/ui/ui.dart';

import '../support/typed_action_items_screen.dart';

void main() {
  for (final brightness in Brightness.values) {
    testWidgets('empty Tasks keeps its icon, guidance and create action in $brightness', (tester) async {
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
      expect(create, findsOneWidget);
      expect(tester.widget<Text>(title).style!.color, OmiColors.textPrimary);
      expect(tester.widget<Text>(hint).style!.color, OmiColors.textSecondary);
      expect(IconTheme.of(tester.element(icon)).color, OmiColors.textTertiary);
      final emptyTitleRect = tester.getRect(title);

      await tester.tap(create);
      await tester.pumpAndSettle();
      expect(find.byType(ActionItemFormSheet), findsOneWidget);
      await tester.tap(find.text(l10n.cancel));
      await tester.pumpAndSettle();
      expect(find.byType(ActionItemFormSheet), findsNothing);

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
      expect(create, findsOneWidget);
      expect(tester.getRect(title), emptyTitleRect);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 1));
    });
  }
}
