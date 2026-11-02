import 'dart:convert';
import 'dart:isolate';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/off_ui_isolate.dart';

// INV-PERF-1: production Home pages and the detail open decode through the
// typed ConversationApi. Moving to it once put the whole page decode (full
// transcripts) back on the UI isolate, on every load-more while scrolling and
// on every tap into a conversation. These decoders refuse to run on the UI isolate.
ApiResult<List<ServerConversation>> _rowsOffUiOnly(String body) {
  if (Isolate.current.debugName != 'conversation_parse') throw StateError('list page decoded on the UI isolate');
  return decodeConversationRows(body);
}

ServerConversation _detailOffUiOnly(String body) {
  if (Isolate.current.debugName != 'conversation_parse') throw StateError('detail decoded on the UI isolate');
  return decodeConversationDetail(body);
}

ServerConversation _conversation(int i, {int segments = 200}) => ServerConversation(
      id: 'c$i',
      createdAt: DateTime.utc(2026, 10, 1).add(Duration(minutes: i)),
      structured: Structured('Conversation $i', 'Overview $i', emoji: '', category: 'other'),
      transcriptSegments: [
        for (var s = 0; s < segments; s++)
          TranscriptSegment(
            id: 'c$i-s$s',
            text: 'Line $s of conversation $i, long enough to look like a real spoken sentence.',
            speaker: 'SPEAKER_0${s % 3}',
            isUser: s % 3 == 0,
            personId: null,
            start: s * 4.0,
            end: s * 4.0 + 3.5,
            translations: const [],
          ),
      ],
    );

void main() {
  late int previousThreshold;
  late ApiResult<List<ServerConversation>> Function(String) previousRows;
  late ServerConversation Function(String) previousDetail;

  setUp(() {
    previousThreshold = conversationListBackgroundParseBytes;
    previousRows = conversationRowsDecoder;
    previousDetail = conversationDetailDecoder;
    offUiIsolateFallbacks = 0;
  });
  tearDown(() {
    conversationListBackgroundParseBytes = previousThreshold;
    conversationRowsDecoder = previousRows;
    conversationDetailDecoder = previousDetail;
  });

  ConversationApi api(String body) => ConversationApi(
        baseUrl: 'http://127.0.0.1:1/',
        send: (_) async => http.Response(body, 200, headers: {'content-type': 'application/json'}),
      );

  test('a 50-conversation Home page with transcripts decodes off the UI isolate', () async {
    final body = jsonEncode([for (var i = 0; i < 50; i++) _conversation(i).toJson()]);
    // ignore: avoid_print
    print('CONVERSATION_PAGE bytes=${body.length}');
    expect(body.length, greaterThan(conversationListBackgroundParseBytes));
    conversationRowsDecoder = _rowsOffUiOnly;

    final result = await api(body).list();

    final rows = (result as ApiSuccess<List<ServerConversation>>).data;
    expect(rows.map((c) => c.id), [for (var i = 0; i < 50; i++) 'c$i']);
    expect(rows.first.transcriptSegments, hasLength(200));
    expect(result.rejectedRows, 0);
    expect(offUiIsolateFallbacks, 0);
  });

  test('a rejected row still comes back counted after the isolate hop', () async {
    final rows = [for (var i = 0; i < 3; i++) _conversation(i, segments: 2).toJson()];
    final body = jsonEncode([...rows, 'not a conversation']);
    conversationListBackgroundParseBytes = 0;
    conversationRowsDecoder = _rowsOffUiOnly;

    final result = await api(body).list() as ApiSuccess<List<ServerConversation>>;

    expect(result.data, hasLength(3));
    expect(result.rejectedRows, 1);
    expect(offUiIsolateFallbacks, 0);
  });

  test('opening a long conversation decodes its detail body off the UI isolate', () async {
    final body = jsonEncode(_conversation(7, segments: 1200).toJson());
    expect(body.length, greaterThan(conversationListBackgroundParseBytes));
    conversationDetailDecoder = _detailOffUiOnly;

    final result = await api(body).byId('c7');

    final conversation = (result as ApiSuccess<ServerConversation>).data;
    expect(conversation.id, 'c7');
    expect(conversation.transcriptSegments, hasLength(1200));
    expect(offUiIsolateFallbacks, 0);
  });

  test('a malformed detail body is still a decode failure', () async {
    conversationListBackgroundParseBytes = 0;
    final result = await api('[1, 2]').byId('x');
    expect(result, isA<ApiFailure<ServerConversation>>());
    expect((result as ApiFailure).problem.kind, ApiProblemKind.decode);
  });
}
