import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/env/env.dart';

/// Outcome of undoing a chat edit receipt.
class EditReceiptUndoResult {
  const EditReceiptUndoResult({required this.undoneAt, this.alreadyUndone = false, this.block});

  /// When the change was undone: the server's time when it sent one, otherwise
  /// the local time the undo succeeded. Null when the server answered
  /// `unavailable` (the undo window closed or the inverse is ambiguous).
  final String? undoneAt;

  /// The server had already undone this receipt (a repeat call is idempotent).
  final bool alreadyUndone;

  /// The updated block, when the server returned it.
  final EditReceiptContentBlock? block;
}

/// `POST /v1/chat/receipts/{receiptId}/undo`. Owner-checked and idempotent on
/// the server; a second call reports `already_undone` and is still a success.
class ChatReceiptsApi {
  const ChatReceiptsApi({this.send, this.baseUrl, this.now});

  final ApiSend? send;
  final String? baseUrl;
  final DateTime Function()? now;

  Future<ApiResult<EditReceiptUndoResult>> undo(String receiptId) {
    final base = baseUrl ?? Env.apiBaseUrl ?? '';
    final root = base.endsWith('/') ? base : '$base/';
    return executeApi(
      request: ApiRequest(
        url: '${root}v1/chat/receipts/${Uri.encodeComponent(receiptId)}/undo',
        method: 'POST',
      ),
      send: send,
      decode: (body) => decodeUndoResponse(body, now: now ?? DateTime.now),
    );
  }

  /// Accepts the backend's `{"status": "undone|already_undone|unavailable",
  /// "block": {…}}`, a bare `editReceipt` block, or an empty body. Anything else
  /// that is not JSON is a decode failure.
  static EditReceiptUndoResult decodeUndoResponse(String body, {required DateTime Function() now}) {
    final fallbackTime = now().toUtc().toIso8601String();
    if (body.trim().isEmpty) return EditReceiptUndoResult(undoneAt: fallbackTime);
    final Object? value;
    try {
      value = jsonDecode(body);
    } on FormatException {
      throw const FormatException('Invalid undo response');
    }
    if (value is! Map) throw const FormatException('Invalid undo response');
    final row = Map<String, dynamic>.from(value);
    final status = row['status'];
    final rawBlock = row['block'] is Map ? Map<String, dynamic>.from(row['block'] as Map) : row;
    final decoded = rawBlock['type'] == null ? null : ChatContentBlock.tryDecode(rawBlock);
    final block = decoded is EditReceiptContentBlock ? decoded : null;
    if (status == 'unavailable') {
      return EditReceiptUndoResult(undoneAt: block?.undoneAt, block: block);
    }
    return EditReceiptUndoResult(
      undoneAt: block?.undoneAt ?? (row['undoneAt'] ?? row['undone_at']) as String? ?? fallbackTime,
      alreadyUndone: status == 'already_undone',
      block: block,
    );
  }
}
