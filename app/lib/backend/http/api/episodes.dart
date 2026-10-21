import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/gen/episodes_wire.g.dart' as wire;
import 'package:omi/env/env.dart';

/// Episodes. Every call returns a typed [ApiResult]. With the server's kill switch off the reads
/// answer `enabled: false`; an older backend answers 404, which callers treat the same way.

Map<String, dynamic> _object(String body) {
  final json = jsonDecode(body);
  if (json is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
  return json;
}

String _id(String id) => Uri.encodeComponent(id);

EpisodeRead _read(Map<String, dynamic> json) {
  final enabled = json['enabled'] == true;
  final episode = json['episode'];
  return EpisodeRead(
    enabled: enabled,
    episode: enabled && episode is Map<String, dynamic>
        ? Episode.fromGenerated(wire.GeneratedEpisode.fromJson(episode))
        : null,
  );
}

Future<ApiResult<EpisodeRead>> getLiveEpisode() => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/episodes/live', method: 'GET'),
      decode: (body) => _read(_object(body)),
    );

Future<ApiResult<EpisodeRead>> getEpisodeForConversation(String conversationId) => executeApi(
      request: ApiRequest(url: '${Env.apiBaseUrl}v1/episodes/by-conversation/${_id(conversationId)}', method: 'GET'),
      decode: (body) => _read(_object(body)),
    );

/// "Wrap up now". With [conversationId] (the capture being finished) the server closes the episode
/// once that conversation's notes are done.
Future<ApiResult<Episode>> wrapUpEpisode(String episodeId, {String? conversationId}) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/episodes/${_id(episodeId)}/wrap-up',
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(wire.GeneratedEpisodeWrapUpRequest(conversationId: conversationId).toJson()),
      ),
      decode: (body) => Episode.fromGenerated(wire.GeneratedEpisode.fromJson(_object(body))),
    );

/// Undo on a captured item: it is dismissed and never becomes a task.
Future<ApiResult<Episode>> dismissEpisodeItem(String episodeId, String itemId) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/episodes/${_id(episodeId)}/items/${_id(itemId)}/dismiss',
        method: 'POST',
      ),
      decode: (body) => Episode.fromGenerated(wire.GeneratedEpisode.fromJson(_object(body))),
    );
