import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/schema/person.dart';

Map<String, dynamic> _personJson(
  String id,
  String name, {
  int? conversationCount,
  String? lastHeardAt,
  double? talkSeconds,
  int? autoConversationCount,
}) =>
    {
      'id': id,
      'name': name,
      'created_at': '2026-01-01T00:00:00Z',
      'updated_at': '2026-01-01T00:00:00Z',
      if (conversationCount != null) 'conversation_count': conversationCount,
      if (lastHeardAt != null) 'last_heard_at': lastHeardAt,
      if (talkSeconds != null) 'talk_seconds': talkSeconds,
      if (autoConversationCount != null) 'auto_conversation_count': autoConversationCount,
    };

http.Response _response(Object body, {int statusCode = 200, Map<String, String> headers = const {}}) =>
    http.Response(body is String ? body : jsonEncode(body), statusCode, headers: headers);

void main() {
  test('a 200 without the truncation header reports complete stats', () {
    final result = PeopleListResponse.fromResponse(_response([_personJson('p-1', 'Alice')]));

    expect(result, isNotNull);
    expect(result!.statsTruncated, isFalse);
    expect(result.people.map((p) => p.id), ['p-1']);
  });

  test('the literal true value under a mixed-case header name marks the stats truncated', () {
    final result = PeopleListResponse.fromResponse(
        _response([_personJson('p-1', 'Alice')], headers: {'X-OMI-List-Truncated': 'true'}));

    expect(result!.statsTruncated, isTrue);
  });

  test('other header values are not treated as truncated', () {
    for (final value in ['false', 'TRUE', 'yes', '']) {
      final result = PeopleListResponse.fromResponse(
          _response([_personJson('p-1', 'Alice')], headers: {'x-omi-list-truncated': value}));
      expect(result!.statsTruncated, isFalse, reason: 'value: $value');
    }
  });

  test('a non-200 response yields null', () {
    for (final statusCode in [400, 401, 500]) {
      expect(PeopleListResponse.fromResponse(_response([_personJson('p-1', 'Alice')], statusCode: statusCode)), isNull);
    }
  });

  test('people are sorted by name with their stats and color indices intact', () {
    final result = PeopleListResponse.fromResponse(_response([
      _personJson('p-b', 'Zed',
          conversationCount: 7, lastHeardAt: '2026-02-01T10:00:00Z', talkSeconds: 300.0, autoConversationCount: 3),
      _personJson('p-a', 'Alice', conversationCount: 1),
    ]));

    expect(result!.people.map((p) => p.id), ['p-a', 'p-b']);
    final zed = result.people.last;
    expect(zed.conversationCount, 7);
    expect(zed.lastHeardAt, DateTime.parse('2026-02-01T10:00:00Z').toLocal());
    expect(zed.talkSeconds, 300.0);
    expect(zed.autoConversationCount, 3);
    expect(zed.colorIdx, 0 % speakerColors.length);
  });

  test('an empty 200 list still reports the truncation flag', () {
    final truncated = PeopleListResponse.fromResponse(_response('[]', headers: {'x-omi-list-truncated': 'true'}));
    expect(truncated!.people, isEmpty);
    expect(truncated.statsTruncated, isTrue);

    final complete = PeopleListResponse.fromResponse(_response('[]'));
    expect(complete!.people, isEmpty);
    expect(complete.statsTruncated, isFalse);
  });
}
