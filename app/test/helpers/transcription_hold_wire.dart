import 'dart:convert';

import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';

import 'home_fixture_env.dart';

/// The wire copies the backend sends for a server-batch recording held for transcription (stored
/// `status: completed`, `record_lane_owner` a batch owner, a transcription deadline, no transcript,
/// no stored or user title). Derived from backend code, not invented:
///
/// - (a) Home/list row: `backend/routers/conversations.py` `get_conversations` applies
///   `transcribing_hold.project(home_step.project(row))` to list-field rows (no transcript).
///   Past the deadline `home_step.classify` says `failed`, and `transcribing_hold.project` keeps
///   `status: completed`, writes the `transcription_presentation` title "Couldn't transcribe" and
///   `summary_retryable: false`, and with no failure receipt `transcription_wait: overdue`.
/// - (b) Detail: `get_conversation_by_id` returns `transcribing_hold.project(conversation)` on the
///   hydrated row: the same status, title and `summary_retryable`, an empty transcript, and no
///   `home_step` (only list reads run `home_step.project`).
/// - (c) Reprocess 200 inside the window: `reprocess_conversation` returns
///   `transcribing_hold.retry_wire(row)`: `status: processing`, `home_step: transcribing`,
///   `summary_retryable: false`, title "Transcribing…", empty transcript.
/// - (d) Reprocess past the window: `retry_wire` returns None and the route answers 409 with
///   [heldReprocess409Body].
const heldConversationId = 'held-recording';

Map<String, dynamic> _stored() => {
      'id': heldConversationId,
      'created_at': '2026-11-16T09:00:00Z',
      'started_at': '2026-11-16T09:00:00Z',
      'finished_at': '2026-11-16T09:08:00Z',
      'source': 'omi',
      'language': 'en',
      'discarded': false,
      'structured': {'title': '', 'overview': '', 'emoji': '🧠', 'category': 'other'},
    };

Map<String, dynamic> _titled(Map<String, dynamic> row, String title) => {
      ...row,
      'structured': {...row['structured'] as Map<String, dynamic>, 'title': title},
    };

/// (a) The Home/list row past its transcription deadline.
Map<String, dynamic> heldListRowJson() => {
      ..._titled(_stored(), "Couldn't transcribe"),
      'status': 'completed',
      'home_step': 'failed',
      'summary_retryable': false,
      'transcription_wait': 'overdue',
    };

/// (b) The detail copy of the same recording.
Map<String, dynamic> heldDetailJson() => {
      ..._titled(_stored(), "Couldn't transcribe"),
      'status': 'completed',
      'summary_retryable': false,
      'transcription_wait': 'overdue',
      'transcript_segments': <Object>[],
    };

/// (c) The reprocess answer while the recording is still inside its transcription window.
Map<String, dynamic> heldRetryWaitingJson() => {
      ..._titled(_stored(), 'Transcribing…'),
      'status': 'processing',
      'home_step': 'transcribing',
      'summary_retryable': false,
      'transcript_segments': <Object>[],
    };

/// (d) The reprocess 409 body past the window.
const heldReprocess409Body = {
  'detail': {
    'code': 'transcription_pending',
    'message': 'Audio is awaiting transcription; summary retry cannot transcribe it',
  },
};

ServerConversation heldListRow() => ServerConversation.fromJson(heldListRowJson());
ServerConversation heldDetail() => ServerConversation.fromJson(heldDetailJson());
ServerConversation heldRetryWaiting() => ServerConversation.fromJson(heldRetryWaitingJson());

http.Response heldJsonResponse(int status, Object body) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json; charset=utf-8'});

/// Call once per test file (setUpAll) before [heldWireReprocess]: the reprocess route reads
/// [Env.apiBaseUrl], and the transport is replaced so nothing is sent.
void initHeldWireEnv() => Env.init(HomeFixtureEnv());

/// The detail page's reprocess call through the real [reProcessConversationServer], with the
/// transport answering [status] and [body]. Records each conversation id in [calls].
ConversationReprocessCall heldWireReprocess(int status, Object body, {List<String>? calls}) {
  return (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) {
    calls?.add(id);
    return reProcessConversationServer(
      id,
      appId: appId,
      requireSpeakerReceipt: requireSpeakerReceipt,
      forceOmi: forceOmi,
      send: (_) async => heldJsonResponse(status, body),
    );
  };
}
