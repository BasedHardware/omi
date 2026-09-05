import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/memory_review.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/widgets/components/memory_review_card.dart';

Memory _memory({required String id, String content = 'Prefers async standups', bool? userReview, bool edited = false}) {
  return Memory(
    id: id,
    uid: 'review-card-user',
    content: content,
    category: MemoryCategory.system,
    createdAt: DateTime.utc(2026, 9, 1),
    updatedAt: DateTime.utc(2026, 9, 1),
    visibility: MemoryVisibility.private,
    userReview: userReview,
    edited: edited,
  );
}

MemoryReviewItem _item(String id, {String content = 'Prefers async standups', String category = 'work'}) {
  return MemoryReviewItem(memoryId: id, content: content, category: category);
}

MemoriesProvider _provider({
  List<Memory> rows = const [],
  ReviewMemoryRequest? reviewMemoryRequest,
  EditMemoryRequest? editMemoryRequest,
}) {
  return MemoriesProvider(
    fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
        GetMemoriesResult(rows, true),
    fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
        const GetLedgerHistoryResult([], supported: true),
    reviewMemoryRequest: reviewMemoryRequest ?? (id, value) async => true,
    editMemoryRequest: editMemoryRequest ?? (id, value) async => const EditMemoryResult(persisted: true),
  );
}

/// A provider whose next fetch reflects later mutations of [rows], so a test can
/// model a refresh that carries another device's verdict or a ledger append.
MemoriesProvider _mutableProvider(List<Memory> rows) {
  return MemoriesProvider(
    fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
        GetMemoriesResult(List<Memory>.from(rows), true),
    fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
        const GetLedgerHistoryResult([], supported: true),
    reviewMemoryRequest: (id, value) async => true,
    editMemoryRequest: (id, value) async => const EditMemoryResult(persisted: true),
  );
}

Widget _harness(MemoriesProvider provider, List<MemoryReviewItem> items) {
  return ChangeNotifierProvider<MemoriesProvider>.value(
    value: provider,
    child: MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(
        body: SingleChildScrollView(
          child: MemoryReviewCard(items: items, source: MemoryReviewSource.chatBlock),
        ),
      ),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'review-card-user'});
    await SharedPreferencesUtil.init();
  });

  testWidgets('renders one row per learned memory with all three controls', (tester) async {
    final provider = _provider(
      rows: [
        _memory(id: 'mem-1'),
        _memory(id: 'mem-2', content: 'Runs on Tuesdays'),
      ],
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-1'), _item('mem-2', content: 'Runs on Tuesdays')]));
    await tester.pump();

    expect(find.text('Things I learned today'), findsOneWidget);
    expect(find.text('Prefers async standups'), findsOneWidget);
    expect(find.text('Runs on Tuesdays'), findsOneWidget);
    expect(find.text('Work'), findsNWidgets(2));
    for (final id in ['mem-1', 'mem-2']) {
      expect(find.byKey(Key('memory_review_accept_$id')), findsOneWidget);
      expect(find.byKey(Key('memory_review_reject_$id')), findsOneWidget);
      expect(find.byKey(Key('memory_review_fix_$id')), findsOneWidget);
    }
  });

  testWidgets('caps the card at three rows', (tester) async {
    final rows = List.generate(5, (i) => _memory(id: 'mem-$i', content: 'fact $i'));
    final provider = _provider(rows: rows);
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, rows.map((m) => _item(m.id, content: m.content)).toList()));
    await tester.pump();

    expect(find.byKey(const Key('memory_review_row_mem-2')), findsOneWidget);
    expect(find.byKey(const Key('memory_review_row_mem-3')), findsNothing);
  });

  testWidgets('accepting paints optimistically before the request returns and calls the provider', (tester) async {
    final completer = Completer<bool>();
    final requested = <bool>[];
    final provider = _provider(
      rows: [_memory(id: 'mem-1')],
      reviewMemoryRequest: (id, value) {
        requested.add(value);
        return completer.future;
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-1')]));
    await tester.pump();

    await tester.tap(find.byKey(const Key('memory_review_accept_mem-1')));
    await tester.pump();

    expect(requested, [true]);
    expect(find.text("Confirmed. I'll act on this."), findsOneWidget);
    expect(find.byKey(const Key('memory_review_accept_mem-1')), findsNothing);

    completer.complete(true);
    await tester.pumpAndSettle();

    // Settled state is read back from the live memory, not from the tap.
    expect(provider.memories.single.userReview, isTrue);
    expect(find.text("Confirmed. I'll act on this."), findsOneWidget);
  });

  testWidgets('rejecting records the negative verdict and dims the row without a layout jump', (tester) async {
    final requested = <bool>[];
    final provider = _provider(
      rows: [_memory(id: 'mem-1')],
      reviewMemoryRequest: (id, value) async {
        requested.add(value);
        return true;
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-1')]));
    await tester.pump();
    final heightBefore = tester.getSize(find.byKey(const Key('memory_review_row_mem-1'))).height;

    await tester.tap(find.byKey(const Key('memory_review_reject_mem-1')));
    await tester.pumpAndSettle();

    expect(requested, [false]);
    expect(provider.memories.single.userReview, isFalse);
    expect(find.text("Dropped. I'll avoid facts like this."), findsOneWidget);
    expect(tester.getSize(find.byKey(const Key('memory_review_row_mem-1'))).height, heightBefore);
    final opacity = tester.widget<AnimatedOpacity>(
      find.descendant(of: find.byKey(const Key('memory_review_row_mem-1')), matching: find.byType(AnimatedOpacity)),
    );
    expect(opacity.opacity, lessThan(1.0));
  });

  testWidgets('a rejected verdict that does not persist reverts and says so inline', (tester) async {
    final provider = _provider(
      rows: [_memory(id: 'mem-1')],
      reviewMemoryRequest: (id, value) async => false,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-1')]));
    await tester.pump();

    await tester.tap(find.byKey(const Key('memory_review_reject_mem-1')));
    await tester.pumpAndSettle();

    expect(provider.memories.single.userReview, isNull);
    expect(find.byKey(const Key('memory_review_error_mem-1')), findsOneWidget);
    expect(find.text("Dropped. I'll avoid facts like this."), findsNothing);
    // The controls come back so the user can try again.
    expect(find.byKey(const Key('memory_review_reject_mem-1')), findsOneWidget);
  });

  testWidgets('a live verdict cast elsewhere renders without any local tap', (tester) async {
    final provider = _provider(rows: [_memory(id: 'mem-1', userReview: true)]);
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-1')]));
    await tester.pump();

    expect(find.text("Confirmed. I'll act on this."), findsOneWidget);
    expect(find.byKey(const Key('memory_review_accept_mem-1')), findsNothing);
  });

  testWidgets('fix opens a prefilled single-line editor and saves through the provider', (tester) async {
    final edits = <String>[];
    final provider = _provider(
      rows: [_memory(id: 'mem-1')],
      editMemoryRequest: (id, value) async {
        edits.add(value);
        return const EditMemoryResult(persisted: true);
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-1')]));
    await tester.pump();

    await tester.tap(find.byKey(const Key('memory_review_fix_mem-1')));
    await tester.pumpAndSettle();

    final editor = tester.widget<TextField>(find.byKey(const Key('memory_review_editor_mem-1')));
    expect(editor.controller?.text, 'Prefers async standups');
    expect(editor.maxLines, 1);

    await tester.enterText(find.byKey(const Key('memory_review_editor_mem-1')), 'Prefers written standups');
    await tester.tap(find.byKey(const Key('memory_review_save_mem-1')));
    await tester.pumpAndSettle();

    expect(edits, ['Prefers written standups']);
    expect(find.text('Updated.'), findsOneWidget);
    expect(find.byKey(const Key('memory_review_editor_mem-1')), findsNothing);
  });

  testWidgets('an edit that does not persist keeps the editor open and says so inline', (tester) async {
    final provider = _provider(
      rows: [_memory(id: 'mem-1')],
      editMemoryRequest: (id, value) async => const EditMemoryResult(persisted: false),
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-1')]));
    await tester.pump();

    await tester.tap(find.byKey(const Key('memory_review_fix_mem-1')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('memory_review_editor_mem-1')), 'Prefers written standups');
    await tester.tap(find.byKey(const Key('memory_review_save_mem-1')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('memory_review_error_mem-1')), findsOneWidget);
    expect(find.text('Updated.'), findsNothing);
    expect(find.byKey(const Key('memory_review_editor_mem-1')), findsOneWidget);
  });

  testWidgets('loads the memories itself when the provider was never initialised', (tester) async {
    // Nothing in app start-up calls MemoriesProvider.init(); only the memories
    // page does. Chat and the daily summary are usually the first memory
    // surface a session opens, and a never-loaded provider reports
    // `loading == true` forever, so the card must not read that as "a fetch is
    // already in flight".
    final provider = _provider(rows: [_memory(id: 'mem-cold')]);
    addTearDown(provider.dispose);
    expect(provider.loading, isTrue, reason: 'a provider that has never loaded still reports loading');

    await tester.pumpWidget(_harness(provider, [_item('mem-cold')]));
    await tester.pumpAndSettle();

    expect(provider.memories.single.id, 'mem-cold');
    final accept = tester.widget<InkWell>(find.byKey(const Key('memory_review_accept_mem-cold')));
    expect(accept.onTap, isNotNull);
  });

  testWidgets('a correction that replaced the referenced row shows the corrected text', (tester) async {
    // A knowledge-ledger correction appends a replacement under a new id, so
    // the id this card references stops resolving. The row must not fall back
    // to the original learned text while saying "Updated."
    final rows = <Memory>[_memory(id: 'mem-ledger')];
    final provider = _mutableProvider(rows);
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-ledger')]));
    await tester.pump();

    await tester.tap(find.byKey(const Key('memory_review_fix_mem-ledger')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('memory_review_editor_mem-ledger')), 'Prefers written standups');
    await tester.tap(find.byKey(const Key('memory_review_save_mem-ledger')));
    await tester.pumpAndSettle();

    // The ledger append: the referenced id is gone on the next refresh.
    rows.clear();
    await provider.loadMemories();
    await tester.pumpAndSettle();

    expect(find.text('Updated.'), findsOneWidget);
    expect(find.text('Prefers written standups'), findsOneWidget);
    expect(find.text('Prefers async standups'), findsNothing);
  });

  testWidgets('a verdict cast elsewhere after a correction still wins', (tester) async {
    // The optimistic paint is not a permanent override: once the write has
    // persisted the row is derived from live memory state again.
    final row = _memory(id: 'mem-live');
    final provider = _mutableProvider([row]);
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-live')]));
    await tester.pump();

    await tester.tap(find.byKey(const Key('memory_review_fix_mem-live')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('memory_review_editor_mem-live')), 'Prefers written standups');
    await tester.tap(find.byKey(const Key('memory_review_save_mem-live')));
    await tester.pumpAndSettle();
    expect(find.text('Updated.'), findsOneWidget);

    // A verdict cast on another device arrives on the next refresh.
    row.userReview = true;
    await provider.loadMemories();
    await tester.pumpAndSettle();

    expect(find.text("Confirmed. I'll act on this."), findsOneWidget);
    expect(find.text('Updated.'), findsNothing);
  });

  testWidgets('a known memory outside the provider list is still fully tappable', (tester) async {
    final reviews = <String, bool>{};
    final provider = _provider(
      rows: const [],
      reviewMemoryRequest: (id, value) async {
        reviews[id] = value;
        return true;
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-missing')]));
    await tester.pumpAndSettle();

    expect(find.text('Prefers async standups'), findsOneWidget);
    // Identity is enough: a row the bulk list never contained must not render
    // dead control chrome.
    for (final key in [
      const Key('memory_review_accept_mem-missing'),
      const Key('memory_review_reject_mem-missing'),
      const Key('memory_review_fix_mem-missing'),
    ]) {
      expect(tester.widget<InkWell>(find.byKey(key)).onTap, isNotNull);
    }

    await tester.tap(find.byKey(const Key('memory_review_accept_mem-missing')));
    await tester.pumpAndSettle();
    // The verdict reached the server by id even though the row never loaded,
    // and the row says so instead of falling back to tappable controls.
    expect(reviews, {'mem-missing': true});
    expect(find.text("Confirmed. I'll act on this."), findsOneWidget);
  });

  testWidgets('a fix on an unresolved row edits by id and records the correction', (tester) async {
    final edits = <String, String>{};
    final provider = _provider(
      rows: const [],
      editMemoryRequest: (id, value) async {
        edits[id] = value;
        return const EditMemoryResult(persisted: true);
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-missing')]));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('memory_review_fix_mem-missing')));
    await tester.pumpAndSettle();

    // The editor is seeded from the recap text when no live row exists.
    final editor = tester.widget<TextField>(find.byKey(const Key('memory_review_editor_mem-missing')));
    expect(editor.controller?.text, 'Prefers async standups');

    await tester.enterText(find.byKey(const Key('memory_review_editor_mem-missing')), 'Prefers written standups');
    await tester.tap(find.byKey(const Key('memory_review_save_mem-missing')));
    await tester.pumpAndSettle();

    expect(edits, {'mem-missing': 'Prefers written standups'});
    expect(find.text('Updated.'), findsOneWidget);
    expect(find.text('Prefers written standups'), findsOneWidget);
    expect(find.byKey(const Key('memory_review_editor_mem-missing')), findsNothing);
  });

  testWidgets('a failed review on an unresolved row reverts and shows the error line', (tester) async {
    final provider = _provider(
      rows: const [],
      reviewMemoryRequest: (id, value) async => false,
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-missing')]));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('memory_review_reject_mem-missing')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('memory_review_error_mem-missing')), findsOneWidget);
    expect(find.text("Dropped. I'll avoid facts like this."), findsNothing);
    // The controls come back so the user can try again.
    final reject = tester.widget<InkWell>(find.byKey(const Key('memory_review_reject_mem-missing')));
    expect(reject.onTap, isNotNull);
  });

  testWidgets('a truncated bulk list does not disable the recap rows', (tester) async {
    // GET /v3/memories can return X-Omi-List-Truncated; the provider stops
    // paging there, so the recap ids can be permanently absent from the list.
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          const GetMemoriesResult([], true, truncated: true),
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
      editMemoryRequest: (id, value) async => const EditMemoryResult(persisted: true),
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-beyond')]));
    await tester.pumpAndSettle();

    expect(provider.memories, isEmpty);
    final accept = tester.widget<InkWell>(find.byKey(const Key('memory_review_accept_mem-beyond')));
    expect(accept.onTap, isNotNull);
  });

  testWidgets('a persisted verdict on an unresolved row survives card State recreation', (tester) async {
    // A chat-list card scrolled out and back rebuilds its State; the settled
    // verdict lives on the provider, so the recreated card must not re-offer
    // a vote the server already recorded.
    final provider = _provider(rows: const [], reviewMemoryRequest: (id, value) async => true);
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-missing')]));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('memory_review_accept_mem-missing')));
    await tester.pumpAndSettle();
    expect(find.text("Confirmed. I'll act on this."), findsOneWidget);

    // Recreate the State exactly as scrolling away and back does.
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    await tester.pumpWidget(_harness(provider, [_item('mem-missing')]));
    await tester.pumpAndSettle();

    expect(find.text("Confirmed. I'll act on this."), findsOneWidget);
    expect(find.byKey(const Key('memory_review_accept_mem-missing')), findsNothing);
  });

  testWidgets('a failed hydration load is retried and resolves once the backend recovers', (tester) async {
    var fetches = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        fetches++;
        if (fetches == 1) {
          return const GetMemoriesResult([], true,
              statusCode: 503, failureReason: MemoriesFetchFailureReason.httpError);
        }
        return GetMemoriesResult([_memory(id: 'mem-flaky')], true);
      },
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
      editMemoryRequest: (id, value) async => const EditMemoryResult(persisted: true),
    );
    addTearDown(provider.dispose);

    await tester.pumpWidget(_harness(provider, [_item('mem-flaky')]));
    await tester.pumpAndSettle();

    // The first ask failed; the card observed the settled failure on rebuild
    // and spent its capped retry, which resolved the row.
    expect(fetches, 2);
    expect(provider.loadFailed, isFalse);
    expect(provider.memories.single.id, 'mem-flaky');
  });

  testWidgets('a persistently failing backend is not retried past the cap', (tester) async {
    var fetches = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        fetches++;
        return const GetMemoriesResult([], true, statusCode: 503, failureReason: MemoriesFetchFailureReason.httpError);
      },
      fetchLedgerHistoryRequest: ({int limit = 500, int offset = 0}) async =>
          const GetLedgerHistoryResult([], supported: true),
      reviewMemoryRequest: (id, value) async => true,
      editMemoryRequest: (id, value) async => const EditMemoryResult(persisted: true),
    );
    addTearDown(provider.dispose);

    await tester.pumpWidget(_harness(provider, [_item('mem-down')]));
    await tester.pumpAndSettle();

    // First ask plus one capped retry; the budget is spent and the row stays
    // actionable by id instead of fetching forever.
    expect(fetches, 2);
    expect(provider.loadFailed, isTrue);
    final accept = tester.widget<InkWell>(find.byKey(const Key('memory_review_accept_mem-down')));
    expect(accept.onTap, isNotNull);
  });
}
