import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/chat_receipts.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/content_blocks/edit_receipt_block.dart';
import 'package:omi/ui/ui.dart';

EditReceiptContentBlock _block({
  String kind = 'task',
  String action = 'renamed',
  bool undoable = true,
  String? undoneAt,
  String id = 'b-1',
  String summary = 'Renamed the task to "Ship the deck"',
}) {
  return ChatContentBlock.tryDecode({
    'type': 'editReceipt',
    'id': id,
    'receiptId': 'r-$id',
    'targetKind': kind,
    'action': action,
    'targetId': 'target-$id',
    'summary': summary,
    'undoable': undoable,
    'undoneAt': undoneAt,
  }) as EditReceiptContentBlock;
}

void main() {
  setUp(EditReceiptBlock.resetSessionState);

  Future<void> pump(
    WidgetTester tester,
    EditReceiptContentBlock block, {
    EditReceiptTargetOpener? openTarget,
    EditReceiptUndo? undo,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SingleChildScrollView(
            child: EditReceiptBlock(
              block: block,
              openTarget: openTarget ?? (_, __) async => true,
              undo: undo ?? (_) async => const ApiSuccess(EditReceiptUndoResult(undoneAt: '2026-10-11T10:00:00Z')),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
  }

  const kinds = {
    'conversation': (Icons.subject, 'Conversation'),
    'memory': (Icons.psychology_outlined, 'Memory'),
    'task': (Icons.checklist, 'Task'),
    'person': (Icons.people_outline, 'Person'),
  };
  const actions = ['created', 'updated', 'deleted', 'completed', 'uncompleted', 'renamed'];

  for (final kind in kinds.entries) {
    for (final action in actions) {
      testWidgets('${kind.key} $action shows its chip, summary and Undo', (tester) async {
        final opened = <EditReceiptContentBlock>[];
        final block = _block(kind: kind.key, action: action, summary: '$action ${kind.key}');
        await pump(tester, block, openTarget: (_, b) async {
          opened.add(b);
          return true;
        });

        expect(find.byIcon(kind.value.$1), findsOneWidget);
        expect(find.text(kind.value.$2), findsOneWidget);
        expect(find.text('$action ${kind.key}'), findsOneWidget);
        expect(find.byKey(const Key('chat-block-editReceipt-b-1-undo')), findsOneWidget);
        expect(find.text('Undo'), findsOneWidget);

        await tester.tap(find.text('$action ${kind.key}'));
        await tester.pump();
        if (action == 'deleted') {
          expect(opened, isEmpty, reason: 'a deleted item has nothing to open');
        } else {
          expect(opened.single.targetId, 'target-b-1');
        }
      });
    }
  }

  testWidgets('Undo calls the endpoint once and switches to Undone', (tester) async {
    final calls = <String>[];
    await pump(tester, _block(), undo: (receiptId) async {
      calls.add(receiptId);
      return const ApiSuccess(EditReceiptUndoResult(undoneAt: '2026-10-11T10:00:00Z'));
    });

    await tester.tap(find.byKey(const Key('chat-block-editReceipt-b-1-undo')));
    await tester.pump();

    expect(calls, ['r-b-1']);
    expect(find.text('Undone'), findsOneWidget);
    expect(find.byKey(const Key('chat-block-editReceipt-b-1-undo')), findsNothing);
    final card = tester.getRect(find.byKey(const Key('chat-block-editReceipt-b-1')));
    final undone = tester.getRect(find.byKey(const Key('chat-block-editReceipt-b-1-undone')));
    expect(card.right - undone.right, lessThan(24));
  });

  testWidgets('an undone receipt stays undone when its row is rebuilt from the original message', (tester) async {
    await pump(tester, _block());
    await tester.tap(find.byKey(const Key('chat-block-editReceipt-b-1-undo')));
    await tester.pump();

    await tester.pumpWidget(const SizedBox());
    await pump(tester, _block());
    expect(find.text('Undone'), findsOneWidget);
    expect(find.text('Undo'), findsNothing);
  });

  testWidgets('an undo that finishes after the row is gone is still undone when it comes back', (tester) async {
    final gate = Completer<ApiResult<EditReceiptUndoResult>>();
    await pump(tester, _block(), undo: (_) => gate.future);
    await tester.tap(find.byKey(const Key('chat-block-editReceipt-b-1-undo')));
    await tester.pump();

    await tester.pumpWidget(const SizedBox());
    gate.complete(const ApiSuccess(EditReceiptUndoResult(undoneAt: '2026-10-11T10:00:00Z')));
    await tester.pump();

    await pump(tester, _block());
    expect(find.text('Undone'), findsOneWidget);
    expect(find.text('Undo'), findsNothing);
  });

  testWidgets('a failed undo keeps Undo and reports the error', (tester) async {
    await pump(tester, _block(),
        undo: (_) async => const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 500)));

    await tester.tap(find.byKey(const Key('chat-block-editReceipt-b-1-undo')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.text("Couldn't undo that change"), findsOneWidget);
    expect(find.byKey(const Key('chat-block-editReceipt-b-1-undo')), findsOneWidget);
    expect(find.text('Undone'), findsNothing);
  });

  for (final outcome in <String, ApiResult<EditReceiptUndoResult>>{
    'unavailable': const ApiSuccess(EditReceiptUndoResult(undoneAt: null)),
    '409': const ApiFailure(ApiProblem(ApiProblemKind.rejected, statusCode: 409)),
    '404': const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404)),
  }.entries) {
    testWidgets('an undo the server refuses (${outcome.key}) drops Undo and says so', (tester) async {
      await pump(tester, _block(), undo: (_) async => outcome.value);

      await tester.tap(find.byKey(const Key('chat-block-editReceipt-b-1-undo')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.text("Couldn't undo that change"), findsOneWidget);
      expect(find.byKey(const Key('chat-block-editReceipt-b-1-undo')), findsNothing);
      expect(find.text('Undone'), findsNothing);

      await tester.pumpWidget(const SizedBox());
      await pump(tester, _block(), undo: (_) async => outcome.value);
      expect(find.byKey(const Key('chat-block-editReceipt-b-1-undo')), findsNothing);
      expect(find.text('Undone'), findsNothing);
    });
  }

  testWidgets('a receipt the server already undid shows Undone without a button', (tester) async {
    await pump(tester, _block(undoneAt: '2026-10-11T09:00:00Z'));
    expect(find.text('Undone'), findsOneWidget);
    expect(find.text('Undo'), findsNothing);
  });

  testWidgets('a receipt that cannot be undone shows no Undo', (tester) async {
    await pump(tester, _block(undoable: false));
    expect(find.text('Undo'), findsNothing);
    expect(find.text('Undone'), findsNothing);
  });

  testWidgets('undoing a delete makes the item openable again; undoing a create removes the link', (tester) async {
    final opened = <String>[];
    Future<bool> open(BuildContext _, EditReceiptContentBlock b) async {
      opened.add(b.action.name);
      return true;
    }

    await pump(tester, _block(action: 'deleted', undoneAt: '2026-10-11T09:00:00Z'), openTarget: open);
    await tester.tap(find.byKey(const Key('chat-block-editReceipt-b-1-summary')));
    await tester.pump();
    expect(opened, ['deleted']);

    await pump(tester, _block(id: 'b-2', action: 'created', undoneAt: '2026-10-11T09:00:00Z'), openTarget: open);
    await tester.tap(find.byKey(const Key('chat-block-editReceipt-b-2-summary')));
    await tester.pump();
    expect(opened, ['deleted']);
  });

  testWidgets('a target that is gone says so', (tester) async {
    await pump(tester, _block(), openTarget: (_, __) async => false);
    await tester.tap(find.byKey(const Key('chat-block-editReceipt-b-1-summary')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('No longer available'), findsOneWidget);
  });

  testWidgets('an unknown kind degrades safely: summary, no destination, Undo still works', (tester) async {
    final opened = <EditReceiptContentBlock>[];
    final calls = <String>[];
    await pump(
      tester,
      _block(kind: 'calendar_event', action: 'moved', summary: 'Moved the standup'),
      openTarget: (_, b) async {
        opened.add(b);
        return true;
      },
      undo: (id) async {
        calls.add(id);
        return const ApiSuccess(EditReceiptUndoResult(undoneAt: '2026-10-11T10:00:00Z'));
      },
    );

    expect(tester.takeException(), isNull);
    expect(find.text('Moved the standup'), findsOneWidget);
    expect(find.byIcon(Icons.edit_outlined), findsOneWidget);

    await tester.tap(find.text('Moved the standup'));
    await tester.pump();
    expect(opened, isEmpty);

    await tester.tap(find.text('Undo'));
    await tester.pump();
    expect(calls, ['r-b-1']);
    expect(find.text('Undone'), findsOneWidget);
  });

  testWidgets('the receipt names itself and its Undo control', (tester) async {
    await pump(tester, _block());
    expect(find.bySemanticsLabel('Task: Renamed the task to "Ship the deck"'), findsOneWidget);
    expect(find.bySemanticsLabel('Undo'), findsOneWidget);
    final card = tester.getRect(find.byKey(const Key('chat-block-editReceipt-b-1')));
    final undo = tester.getRect(find.byKey(const Key('chat-block-editReceipt-b-1-undo')));
    expect(card.right - undo.right, lessThan(24));
  });

  for (final brightness in Brightness.values) {
    for (final scale in [2.0, 3.0]) {
      testWidgets('no overflow at text scale $scale in ${brightness.name}', (tester) async {
        tester.view.physicalSize = const Size(320, 800);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final previousPalette = OmiColors.active;
        OmiColors.active = brightness == Brightness.dark ? OmiPalette.dark : OmiPalette.light;
        addTearDown(() => OmiColors.active = previousPalette);
        await tester.pumpWidget(
          MaterialApp(
            theme: ThemeData(brightness: brightness),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            builder: (context, child) => MediaQuery(
              data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)),
              child: child ?? const SizedBox.shrink(),
            ),
            home: Scaffold(
              body: EditReceiptBlock(
                block: _block(
                  kind: 'conversation',
                  summary: 'Renamed the conversation to "Pricing sync with the whole team"',
                ),
                openTarget: (_, __) async => true,
                undo: (_) async => const ApiSuccess(EditReceiptUndoResult(undoneAt: '2026-10-11T10:00:00Z')),
              ),
            ),
          ),
        );
        await tester.pump();
        expect(tester.takeException(), isNull);
        expect(find.text('Undo'), findsOneWidget);
        expect(find.text('Conversation'), findsOneWidget);
      });
    }
  }
}
