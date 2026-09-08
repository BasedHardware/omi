import 'dart:async';

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

class _RevertProvider extends MemoriesProvider {
  final Completer<bool> result = Completer<bool>();
  int calls = 0;
  bool inFlight = false;

  @override
  bool canRevertSupersededFact(Memory memory) =>
      memory.ledgerSchemaVersion == 'knowledge_ledger.v1' &&
      memory.ledgerKind == KnowledgeLedgerKind.fact &&
      memory.intentBacked &&
      memory.userReview != false &&
      memory.invalidAt != null &&
      (memory.supersededBy ?? '').trim().isNotEmpty;

  @override
  bool isRevertingMemory(String memoryId) => inFlight;

  @override
  Future<bool> revertSupersededFact(Memory memory) async {
    if (inFlight) return false;
    calls++;
    inFlight = true;
    notifyListeners();
    final persisted = await result.future;
    inFlight = false;
    notifyListeners();
    return persisted;
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

Memory _fact({
  bool? userReview,
  String? supersededBy,
  DateTime? invalidAt,
  KnowledgeLedgerKind kind = KnowledgeLedgerKind.fact,
  String schemaVersion = 'knowledge_ledger.v1',
  bool intentBacked = true,
}) {
  return Memory(
    id: 'fact-1',
    uid: 'user-1',
    content: 'Lives in Brooklyn',
    category: MemoryCategory.system,
    createdAt: DateTime.utc(2026, 8, 23),
    updatedAt: DateTime.utc(2026, 8, 23),
    visibility: MemoryVisibility.private,
    ledgerSchemaVersion: schemaVersion,
    ledgerKind: kind,
    ledgerSlot: 'home_city',
    intentBacked: intentBacked,
    userReview: userReview,
    supersededBy: supersededBy,
    invalidAt: invalidAt,
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

    await pump(_fact(supersededBy: 'replacement', invalidAt: DateTime.utc(2026, 8, 24)));
    await tester.tap(find.text('Lives in Brooklyn'));
    expect(taps, 2);
  });

  testWidgets('eligible superseded v1 fact exposes one accessible revert action', (tester) async {
    final provider = _RevertProvider();
    addTearDown(provider.dispose);
    final memory = _fact(
      supersededBy: 'replacement',
      invalidAt: DateTime.utc(2026, 8, 24),
    );

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

    final action = find.byKey(const Key('memory_revert_superseded_fact_fact-1'));
    expect(action, findsOneWidget);
    expect(find.byTooltip('Undo'), findsOneWidget);
    expect(find.bySemanticsLabel('Undo'), findsOneWidget);
    expect(tester.getSize(action), const Size(48, 48));
  });

  testWidgets('revert action is disabled in flight and reports canonical failure', (tester) async {
    final provider = _RevertProvider();
    addTearDown(provider.dispose);
    final memory = _fact(supersededBy: 'replacement', invalidAt: DateTime.utc(2026, 8, 24));

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

    final action = find.byKey(const Key('memory_revert_superseded_fact_fact-1'));
    await tester.tap(action);
    await tester.pump();
    expect(provider.calls, 1);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    await tester.tap(action);
    await tester.pump();
    expect(provider.calls, 1);

    provider.result.complete(false);
    await tester.pumpAndSettle();
    expect(find.text('Something went wrong! Please try again later.'), findsOneWidget);
  });

  testWidgets('revert action excludes closed, rejected-current, non-fact, future, and legacy rows', (tester) async {
    final provider = _RevertProvider();
    addTearDown(provider.dispose);
    final excluded = [
      _fact(invalidAt: DateTime.utc(2026, 8, 24)),
      _fact(supersededBy: 'replacement'),
      _fact(userReview: false),
      _fact(supersededBy: 'replacement', kind: KnowledgeLedgerKind.document),
      _fact(supersededBy: 'replacement', schemaVersion: 'knowledge_ledger.v2'),
      _fact(supersededBy: 'replacement', schemaVersion: ''),
    ];

    for (final memory in excluded) {
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
      expect(find.byKey(const Key('memory_revert_superseded_fact_fact-1')), findsNothing);
    }
  });
}
