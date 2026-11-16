// Recordings-and-conversations (v3) reads: the per-user capability with the live conversation and the
// audio manifest. Wire types and decoders: backend/schema/conversation_v3_wire.dart; the streamed summary:
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

String _id(String id) => Uri.encodeComponent(id);

/// A 404 means an older server: callers treat it as `v3: false`.
Future<ApiResult<ConversationsLiveRead>> getConversationsLive({ApiSend? send}) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/conversations/live', method: 'GET'),
      send: send,
      decode: (body) => ConversationsLiveRead.fromJson(_object(body)),
    );

Future<ApiResult<List<AudioManifestPiece>>> getAudioManifest(String conversationId, {ApiSend? send}) => executeApi(
      request:
          ApiRequest(url: '${Env.apiBaseUrl}v1/conversations/${_id(conversationId)}/audio-manifest', method: 'GET'),
      send: send,
      decode: (body) {
        final pieces = _object(body)['pieces'];
        if (pieces is! List) throw const FormatException('Expected pieces');
        return pieces.map(AudioManifestPiece.fromJson).whereType<AudioManifestPiece>().toList();
      },
    );
