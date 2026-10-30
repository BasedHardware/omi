import 'dart:convert';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/people_wire.g.dart' as wire;
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';

/// What happens after a speaker label: rejecting a wrong one, reading whether a person's voice was
/// learned, and finding the same voice in earlier conversations. Every call returns a typed
/// [ApiResult]; callers decide what an outage means.

Map<String, dynamic> _object(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic>) throw const FormatException('Expected a JSON object');
  return decoded;
}

/// Why the user rejected a label on a voice.
enum SpeakerRejection {
  notMe('not_me'),
  notPerson('not_person'),
  notAPerson('not_a_person');

  const SpeakerRejection(this.wire);
  final String wire;
}

typedef SpeakerRejectionCall = Future<ApiResult<ServerConversation>>
    Function(String conversationId, int speakerId, SpeakerRejection kind, {String? personId, List<String>? segmentIds});

/// Tells Omi a label on [speakerId] in this conversation is wrong, so it is cleared and that voice
/// is not matched the same way again. [personId] is the rejected person for [SpeakerRejection.notPerson].
Future<ApiResult<ServerConversation>> rejectConversationSpeaker(
  String conversationId,
  int speakerId,
  SpeakerRejection kind, {
  String? personId,
  List<String>? segmentIds,
}) =>
    executeApi<ServerConversation>(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/conversations/${Uri.encodeComponent(conversationId)}/speakers/$speakerId/reject',
        method: 'POST',
        body: jsonEncode({
          'kind': kind.wire,
          if (personId != null) 'person_id': personId,
          if (segmentIds != null) 'segment_ids': segmentIds,
        }),
      ),
      decode: (body) => ServerConversation.fromJson(_object(body)),
    );

/// One person, with the server's current voice-learning state.
Future<ApiResult<Person>> getPerson(String personId) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/users/people/${Uri.encodeComponent(personId)}?include_speech_samples=false',
        method: 'GET',
      ),
      decode: (body) => Person.fromJson(_object(body)),
    );

/// An unnamed voice in an earlier conversation that matches a person's learned voice.
typedef PersonVoiceMatch = wire.GeneratedVoiceMatch;

/// Unnamed voices in recent conversations that sound like [personId]. Empty when the person's
/// voice is not learned yet.
Future<ApiResult<List<PersonVoiceMatch>>> getPersonVoiceMatches(String personId) => executeApi(
      request: ApiRequest(
        url: '${Env.apiBaseUrl}v1/users/people/${Uri.encodeComponent(personId)}/voice-matches',
        method: 'GET',
      ),
      decode: (body) => wire.GeneratedVoiceMatchesResponse.fromJson(_object(body)).matches ?? const [],
    );
