import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/reply_draft.dart';
import 'package:omi/env/env.dart';

Future<ReplyDraftResponse> createReplyDraftServer(
  ReplyDraftRequest request,
) async {
  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/reply-drafts',
    headers: {'Content-Type': 'application/json'},
    method: 'POST',
    body: jsonEncode(request.toJson()),
  );

  if (response == null) {
    throw Exception('Could not reach Omi');
  }

  if (response.statusCode == 200) {
    return ReplyDraftResponse.fromJson(jsonDecode(response.body));
  }

  String message = 'Failed to draft reply';
  try {
    final decoded = jsonDecode(response.body);
    if (decoded is Map && decoded['detail'] != null) {
      message = decoded['detail'].toString();
    }
  } catch (_) {}
  throw Exception(message);
}
