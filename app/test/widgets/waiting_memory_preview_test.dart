import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_item.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';

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
            MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(2)), child: child!),
        home: Scaffold(
            body: SizedBox(
                width: 340,
                child: MemoryItem(memory: memory, provider: provider, showDismissible: false, onTap: (_, __, ___) {}))),
      ),
    ));
    expect(find.text('Pending'), findsOneWidget);
    expect(find.text('See plans'), findsOneWidget);
    expect(find.byIcon(Icons.lock_outline), findsNothing);
    expect(find.bySemanticsLabel('OK'), findsNothing);
    final preview = tester.getRect(find.byType(OmiLockedPreview));
    final action = tester.getRect(find.byKey(const Key('locked_preview_action')));
    expect(preview.contains(action.topLeft), isTrue);
    expect(preview.contains(action.bottomRight), isTrue);
    expect(tester.takeException(), isNull);
  });
}
