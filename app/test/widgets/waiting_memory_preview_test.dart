import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_item.dart';
import 'package:omi/pages/memories/widgets/memory_edit_sheet.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';

class _Usage extends UsageProvider {
  _Usage(this.visible);
  final bool visible;
  @override
  bool get showSubscriptionUI => visible;
}

class _Routes extends NavigatorObserver {
  final pushed = <Route<dynamic>>[];
  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) => pushed.add(route);
}

void main() {
  testWidgets('short waiting memory fits its status and action at 200% text', (tester) async {
    final provider = MemoriesProvider();
    final usage = UsageProvider();
    addTearDown(provider.dispose);
    addTearDown(usage.dispose);
    final memory = Memory(
        id: 'held',
        uid: 'fixture',
        content: 'OK',
        category: MemoryCategory.system,
        createdAt: DateTime.utc(2026),
        updatedAt: DateTime.utc(2026),
        visibility: MemoryVisibility.private,
        isLocked: true);
    await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
      value: usage,
      child: MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        builder: (context, child) =>
            MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: const TextScaler.linear(2)), child: child!),
        home: Scaffold(
            body: SizedBox(
                width: 340,
                child: MemoryItem(memory: memory, provider: provider, showDismissible: false, onTap: (_, __, ___) {}))),
      ),
    ));
    expect(find.text('Pending'), findsOneWidget);
    expect(find.text('View Usage'), findsOneWidget);
    expect(find.byIcon(Icons.lock_outline), findsNothing);
    expect(find.bySemanticsLabel('OK'), findsNothing);
    final preview = tester.getRect(find.byType(OmiLockedPreview));
    final action = tester.getRect(find.byKey(const Key('locked_preview_action')));
    expect(preview.contains(action.topLeft), isTrue);
    expect(preview.contains(action.bottomRight), isTrue);
    expect(tester.takeException(), isNull);
  });
  for (final visible in [true, false]) {
    for (final target in ['frost', 'padding', 'button']) {
      testWidgets('held memory $target tap obeys subscription visibility $visible', (tester) async {
        final provider = MemoriesProvider();
        final usage = _Usage(visible);
        final routes = _Routes();
        addTearDown(provider.dispose);
        addTearDown(usage.dispose);
        var editCalls = 0;
        final memory = Memory(
          id: 'held',
          uid: 'fixture',
          content: 'Private held memory',
          category: MemoryCategory.system,
          createdAt: DateTime.utc(2026),
          updatedAt: DateTime.utc(2026),
          visibility: MemoryVisibility.private,
          isLocked: true,
        );
        await tester.pumpWidget(ChangeNotifierProvider<UsageProvider>.value(
          value: usage,
          child: MaterialApp(
            theme: buildOmiTheme(),
            navigatorObservers: [routes],
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: const [Locale('en')],
            home: Scaffold(
                body: Align(
                    alignment: Alignment.topLeft,
                    child: SizedBox(
                        width: 340,
                        child: MemoryItem(
                            memory: memory,
                            provider: provider,
                            showDismissible: false,
                            onTap: (_, __, ___) => editCalls++)))),
          ),
        ));
        final preview = tester.getRect(find.byType(OmiLockedPreview));
        if (target == 'button') {
          await tester.tap(find.byKey(const Key('locked_preview_action')));
        } else {
          // Left edge is outside See plans; padding exercises the enclosing row handler.
          await tester.tapAt(Offset(preview.left + (target == 'padding' ? -10 : 2), preview.center.dy));
        }
        expect(editCalls, 0);
        expect(routes.pushed, hasLength(2));
        if (visible) {
          final destination =
              (routes.pushed.last as MaterialPageRoute).builder(tester.element(find.byType(MemoryItem)));
          expect(destination, isA<UsagePage>());
          expect((destination as UsagePage).showUpgradeDialog, isFalse);
          expect(find.byType(MemoryEditSheet), findsNothing);
          expect(find.byType(SelectableText), findsNothing);
          expect(find.bySemanticsLabel('Private held memory'), findsNothing);
          // Do not build the network-backed usage page.
          await tester.pumpWidget(const SizedBox.shrink());
        } else {
          await tester.pumpAndSettle();
          expect(tester.widget<MemoryEditSheet>(find.byType(MemoryEditSheet)).readOnly, isTrue);
          expect(find.widgetWithText(SelectableText, 'Private held memory'), findsOneWidget);
          expect(find.byKey(const ValueKey('memory_edit_field')), findsNothing);
          expect(find.byType(UsagePage), findsNothing);
          expect(tester.takeException(), isNull);
        }
      });
    }
  }
}
