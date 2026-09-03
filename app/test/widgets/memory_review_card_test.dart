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

Memory _memory({
  required String id,
  String content = 'Prefers async standups',
  bool? userReview,
  bool edited = false,
}) {
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
    final provider = _provider(rows: [_memory(id: 'mem-1'), _memory(id: 'mem-2', content: 'Runs on Tuesdays')]);
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

  testWidgets('an unresolved memory still shows its content with the controls disabled', (tester) async {
    final provider = _provider(rows: const []);
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await tester.pumpWidget(_harness(provider, [_item('mem-missing')]));
    await tester.pumpAndSettle();

    expect(find.text('Prefers async standups'), findsOneWidget);
    final accept = tester.widget<InkWell>(find.byKey(const Key('memory_review_accept_mem-missing')));
    expect(accept.onTap, isNull);
    expect(find.byKey(const Key('memory_review_status_mem-missing')), findsNothing);
  });
}
