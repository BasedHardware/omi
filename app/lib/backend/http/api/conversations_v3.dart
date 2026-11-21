// Recordings-and-conversations (v3) reads: the per-user capability with the live conversation. Audio
// plays from the window-exact conversation artifact through the existing audio routes. Wire types and decoders: backend/schema/conversation_v3_wire.dart; the streamed summary:
// services/conversation_summary_stream.dart.
import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation_v3_wire.dart';
import 'package:omi/env/env.dart';

export 'package:omi/backend/schema/conversation_v3_wire.dart';

Map<String, dynamic> _object(String body) {
  final json = jsonDecode(body);
  if (json is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
  return json;
}

/// A 404 means an older server: callers treat it as `v3: false`.
Future<ApiResult<ConversationsLiveRead>> getConversationsLive({ApiSend? send}) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/conversations/live', method: 'GET'),
      send: send,
      decode: (body) => ConversationsLiveRead.fromGeneratedWireJson(_object(body)),
    );
