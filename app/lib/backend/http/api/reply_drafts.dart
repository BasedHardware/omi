import 'dart:convert';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/reply_draft.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

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
    return ReplyDraftResponse.fromJson(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Logger.debug('createReplyDraftServer error ${response.statusCode}');
  throw Exception('Failed to draft reply (status ${response.statusCode})');
}
