import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/chat_receipts.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/widgets/content_blocks/chat_content_block_list.dart';
import 'package:omi/pages/home/home_deep_links.dart';

Map<String, dynamic> _receipt([Map<String, dynamic> overrides = const {}]) => {
      'type': 'editReceipt',
      'id': 'b-1',
      'receiptId': 'r-1',
      'targetKind': 'task',
      'action': 'renamed',
      'targetId': 't-1',
      'summary': 'Renamed the task to "Ship the deck"',
      'undoable': true,
      'undoneAt': null,
      ...overrides,
    };

void main() {
  group('editReceipt decoding', () {
    test('camelCase wire', () {
      final block = ChatContentBlock.tryDecode(_receipt()) as EditReceiptContentBlock;
      expect(block.type, 'editReceipt');
      expect(block.receiptId, 'r-1');
      expect(block.targetKind, EditReceiptTargetKind.task);
      expect(block.action, EditReceiptAction.renamed);
      expect(block.targetId, 't-1');
      expect(block.summary, 'Renamed the task to "Ship the deck"');
      expect(block.canUndo, isTrue);
      expect(block.isUndone, isFalse);
    });

    test('snake_case wire', () {
      final block = ChatContentBlock.tryDecode({
        'type': 'edit_receipt',
        'id': 'b-2',
        'receipt_id': 'r-2',
        'target_kind': 'memory',
        'action': 'deleted',
        'target_id': 'm-1',
        'summary': 'Deleted a memory',
        'undoable': true,
        'undone_at': '2026-10-11T10:00:00Z',
      }) as EditReceiptContentBlock;
      expect(block.receiptId, 'r-2');
      expect(block.targetKind, EditReceiptTargetKind.memory);
      expect(block.action, EditReceiptAction.deleted);
      expect(block.targetId, 'm-1');
      expect(block.undoneAt, '2026-10-11T10:00:00Z');
      expect(block.canUndo, isFalse);
    });

    test('every kind and action round-trips', () {
      for (final kind in ['conversation', 'memory', 'task', 'person']) {
        for (final action in ['created', 'updated', 'deleted', 'completed', 'uncompleted', 'renamed']) {
          final block =
              ChatContentBlock.tryDecode(_receipt({'targetKind': kind, 'action': action})) as EditReceiptContentBlock;
          expect(block.targetKind.name, kind);
          expect(block.action.name, action);
        }
      }
    });

    test('an unknown kind or action degrades to unknown, not a dropped block', () {
      final block = ChatContentBlock.tryDecode(_receipt({'targetKind': 'calendar_event', 'action': 'moved'}))
          as EditReceiptContentBlock;
      expect(block.targetKind, EditReceiptTargetKind.unknown);
      expect(block.rawTargetKind, 'calendar_event');
      expect(block.action, EditReceiptAction.unknown);
      expect(block.summary, isNotEmpty);
    });

    test('a receipt without a receipt id or summary is dropped', () {
      expect(ChatContentBlock.tryDecode(_receipt({'receiptId': null})), isNull);
      expect(ChatContentBlock.tryDecode(_receipt({'summary': '  '})), isNull);
    });

    test('undoable must be literally true', () {
      final block = ChatContentBlock.tryDecode(_receipt({'undoable': 'yes'})) as EditReceiptContentBlock;
      expect(block.canUndo, isFalse);
    });

    test('the message renders it as a card and falls back to its summary', () {
      final message = ServerMessage.fromJson({
        'id': 'm-1',
        'created_at': '2026-10-11T10:00:00Z',
        'text': '',
        'sender': 'ai',
        'type': 'text',
        'content_blocks': [_receipt()],
      });
      expect(ChatContentBlockList.hasRenderableBlocks(message), isTrue);
      expect(message.text, 'Renamed the task to "Ship the deck"');
      expect(message.textIsStructuredFallback, isTrue);
    });
  });

  group('ChatReceiptsApi.undo', () {
    test('posts to the receipt undo endpoint and reads the returned block', () async {
      late ApiRequest sent;
      final api = ChatReceiptsApi(
        baseUrl: 'https://api.test',
        send: (request) async {
          sent = request;
          return http.Response(
            jsonEncode({
              'status': 'undone',
              'block': _receipt({'undoneAt': '2026-10-11T10:01:00Z', 'undoable': false}),
            }),
            200,
          );
        },
      );
      final result = await api.undo('r/1');
      expect(sent.method, 'POST');
      expect(sent.url, 'https://api.test/v1/chat/receipts/r%2F1/undo');
      final data = (result as ApiSuccess<EditReceiptUndoResult>).data;
      expect(data.undoneAt, '2026-10-11T10:01:00Z');
      expect(data.alreadyUndone, isFalse);
      expect(data.block?.receiptId, 'r-1');
    });

    test('already_undone is a success', () async {
      final api = ChatReceiptsApi(
        baseUrl: 'https://api.test/',
        now: () => DateTime.utc(2026, 10, 11, 12),
        send: (_) async => http.Response(jsonEncode({'status': 'already_undone'}), 200),
      );
      final data = ((await api.undo('r-1')) as ApiSuccess<EditReceiptUndoResult>).data;
      expect(data.alreadyUndone, isTrue);
      expect(data.undoneAt, '2026-10-11T12:00:00.000Z');
    });

    test('a bare block body is accepted', () {
      final data = ChatReceiptsApi.decodeUndoResponse(
        jsonEncode(_receipt({'undoneAt': '2026-10-11T10:02:00Z'})),
        now: DateTime.now,
      );
      expect(data.undoneAt, '2026-10-11T10:02:00Z');
    });

    test('a server failure is a typed failure', () async {
      final api = ChatReceiptsApi(
        baseUrl: 'https://api.test',
        send: (_) async => http.Response('{"detail":"gone"}', 409),
      );
      expect(await api.undo('r-1'), isA<ApiFailure<EditReceiptUndoResult>>());
    });

    test('a non-JSON body is a decode failure', () async {
      final api = ChatReceiptsApi(baseUrl: 'https://api.test', send: (_) async => http.Response('<html>', 200));
      final result = await api.undo('r-1');
      expect((result as ApiFailure<EditReceiptUndoResult>).problem.kind, ApiProblemKind.decode);
    });
  });

  group('h.omi.me item links', () {
    test('singular item paths route into Home', () {
      expect(HomeDeepLink.itemRouteFromAppLink(Uri.parse('https://h.omi.me/conversation/c-1')), '/conversation/c-1');
      expect(HomeDeepLink.itemRouteFromAppLink(Uri.parse('https://h.omi.me/task/t-1')), '/task/t-1');
      expect(HomeDeepLink.itemRouteFromAppLink(Uri.parse('https://h.omi.me/memory/m-1')), '/memory/m-1');
      // The web fallback's iOS button.
      expect(HomeDeepLink.itemRouteFromAppLink(Uri.parse('omi://h.omi.me/task/t-1')), '/task/t-1');
    });

    test('the routes are ones Home already opens', () {
      for (final link in ['/conversation/c-1', '/task/t-1', '/memory/m-1']) {
        final parsed = HomeDeepLink.parse(link)!;
        expect(parsed.id, isNotNull);
        expect(parsed.tabIndex, isNotNull, reason: link);
      }
    });

    test('public share pages and foreign hosts are not item links', () {
      for (final raw in [
        'https://h.omi.me/conversations/c-1',
        'https://h.omi.me/memories/c-1',
        'https://h.omi.me/tasks/token',
        'https://h.omi.me/apps/app-1',
        'https://h.omi.me/conversation',
        'https://h.omi.me/conversation/c-1/extra',
        'https://evil.example/conversation/c-1',
        'http://h.omi.me/conversation/c-1',
      ]) {
        expect(HomeDeepLink.itemRouteFromAppLink(Uri.parse(raw)), isNull, reason: raw);
      }
    });
  });
}
