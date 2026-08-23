import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/memory.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_item.dart';
import 'package:omi/pages/memories/widgets/memory_history_status_banner.dart';
import 'package:omi/providers/memories_provider.dart';

class _ReviewProvider extends MemoriesProvider {
  final List<bool> decisions = [];

  @override
  Future<bool> reviewMemory(Memory memory, bool value) async {
    decisions.add(value);
    memory.userReview = value;
    return true;
  }
}

Memory _playbook() {
  return Memory(
    id: 'playbook-1',
    uid: 'user-1',
    content: 'Release checklist',
    category: MemoryCategory.workflow,
    createdAt: DateTime.utc(2026, 8, 23),
    updatedAt: DateTime.utc(2026, 8, 23),
    visibility: MemoryVisibility.private,
    ledgerSchemaVersion: 'knowledge_ledger.v1',
    ledgerKind: KnowledgeLedgerKind.document,
    ledgerBody: 'Run tests, review the diff, and publish receipts.',
    intentBacked: true,
  );
}

Memory _fact({bool? userReview, String? supersededBy}) {
  return Memory(
    id: 'fact-1',
    uid: 'user-1',
    content: 'Lives in Brooklyn',
    category: MemoryCategory.system,
    createdAt: DateTime.utc(2026, 8, 23),
    updatedAt: DateTime.utc(2026, 8, 23),
    visibility: MemoryVisibility.private,
    ledgerSchemaVersion: 'knowledge_ledger.v1',
    ledgerKind: KnowledgeLedgerKind.fact,
    ledgerSlot: 'home_city',
    intentBacked: true,
    userReview: userReview,
    supersededBy: supersededBy,
  );
}

void main() {
  testWidgets('ledger playbook renders its body and canonical review controls', (tester) async {
    final provider = _ReviewProvider();
    addTearDown(provider.dispose);
    final memory = _playbook();

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: MemoryItem(
            memory: memory,
            provider: provider,
            showDismissible: false,
            onTap: (_, __, ___) {},
          ),
        ),
      ),
    );

    expect(find.text('Release checklist'), findsOneWidget);
    expect(find.text('Run tests, review the diff, and publish receipts.'), findsOneWidget);
    expect(find.byIcon(Icons.menu_book_outlined), findsOneWidget);
    expect(find.byKey(const Key('memory_review_accept_playbook-1')), findsOneWidget);
    expect(find.byKey(const Key('memory_review_reject_playbook-1')), findsOneWidget);

    await tester.tap(find.byKey(const Key('memory_review_reject_playbook-1')));
    await tester.pump();

    expect(provider.decisions, [false]);
    expect(memory.userReview, isFalse);
  });

  testWidgets('a rejected ledger row exposes the reversible accept control', (tester) async {
    final provider = _ReviewProvider();
    addTearDown(provider.dispose);
    final memory = _playbook()..userReview = false;

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: MemoryItem(
            memory: memory,
            provider: provider,
            showDismissible: false,
            onTap: (_, __, ___) {},
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('memory_review_accept_playbook-1')));
    await tester.pump();

    expect(provider.decisions, [true]);
    expect(memory.userReview, isTrue);
  });

  testWidgets('partial history status is explicit and informational', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        localizationsDelegates: [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: MemoryHistoryStatusBanner()),
      ),
    );

    expect(find.text('Some memory history is unavailable. Showing the history received so far.'), findsOneWidget);
    expect(find.byIcon(Icons.info_outline), findsOneWidget);
    expect(find.byType(TextButton), findsNothing);
  });

  testWidgets('current and rejected facts are editable but superseded history is read-only', (tester) async {
    final provider = _ReviewProvider();
    addTearDown(provider.dispose);
    var taps = 0;

    Future<void> pump(Memory memory) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: MemoryItem(
              memory: memory,
              provider: provider,
              showDismissible: false,
              onTap: (_, __, ___) => taps += 1,
            ),
          ),
        ),
      );
    }

    await pump(_fact());
    await tester.tap(find.text('Lives in Brooklyn'));
    expect(taps, 1);

    await pump(_fact(userReview: false));
    await tester.tap(find.text('Lives in Brooklyn'));
    expect(taps, 2, reason: 'review rejection must not make the active fact structurally historical');

    await pump(_fact(supersededBy: 'replacement'));
    await tester.tap(find.text('Lives in Brooklyn'));
    expect(taps, 2);
  });
}
