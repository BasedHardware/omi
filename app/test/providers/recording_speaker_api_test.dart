import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/api/recording_speakers.dart';
import 'package:omi/backend/schema/recording_speakers.dart';
import 'package:omi/env/env.dart';
import '../helpers/recording_speaker_fixtures.dart';

void main() {
  setUpAll(() => Env.init(RecordingSpeakerFixtureEnv()));
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  test('generated recording transcript preserves scope, provider label and recording offset', () {
    final recording = RecordingTranscript.fromResponse(jsonEncode({
      'enabled': true,
      'episode_id': 'episode',
      'conversations': [
        {
          'id': 'c1',
          'recording_offset_seconds': 20,
          'transcript_segments': [
            {
              'id': 'a',
              'text': 'Synthetic speech',
              'start': 0,
              'end': 1,
              'is_user': false,
              'speaker_id_scope': 'scope',
              'stream_speaker': 'SPEAKER_0'
            }
          ]
        }
      ]
    }));
    expect(recording.episodeId, 'episode');
    expect(recording.lines.single.voice, ('scope', 'SPEAKER_0'));
    expect(recording.lines.single.offset, 20);
  });
  test('generated recording transcript retains the disabled switch', () {
    final recording = RecordingTranscript.fromResponse('{"enabled":false,"conversations":[]}');
    expect(recording.enabled, isFalse);
    expect(recording.lines, isEmpty);
  });
  for (final coverage in ['complete', 'partial', null]) {
    test('recording coverage survives transcript and assignment decoding: $coverage', () async {
      final recording = RecordingTranscript.fromResponse(jsonEncode({
        'enabled': true,
        'conversations': [],
        if (coverage != null) 'coverage': coverage,
      }));
      expect(recording.coverageComplete, coverage == 'complete');
      final result = await assignRecordingSpeakers(
          'c1',
          [
            {
              'conversation_id': 'c1',
              'segment_ids': ['a']
            }
          ],
          personId: 'maya',
          wholeRecording: true,
          send: (_) async => http.Response(
              jsonEncode({
                'applied_count': 1,
                'conversations': [
                  {'conversation_id': 'c1', 'applied_count': 1}
                ],
                if (coverage != null) 'coverage': coverage,
              }),
              200));
      expect((result as ApiSuccess<int>).truncated, coverage != 'complete');
    });
  }
  for (final status in [404, 409, 200]) {
    test('disabled or old recording server falls back to explicit per-conversation ids: $status', () async {
      final requests = <ApiRequest>[];
      final result = await assignRecordingSpeakers(
          'c1',
          [
            {
              'conversation_id': 'c1',
              'segment_ids': ['a'],
              'speaker_id': 4,
              'voice': {'speaker_id_scope': 's1', 'stream_speaker': 'SPEAKER_0'}
            }
          ],
          personId: 'maya',
          wholeRecording: true, send: (request) async {
        requests.add(request);
        if (requests.length == 1) {
          return http.Response(
              status == 200 ? '{"enabled":false}' : '{"detail":"recording_speaker_rename_disabled"}', status);
        }
        return http.Response('{}', 200);
      });
      expect(result, isA<ApiSuccess<int>>());
      expect((result as ApiSuccess<int>).truncated, isTrue);
      expect(requests, hasLength(2));
      expect(requests.last.url, contains('/conversations/c1/assign-speaker/4?'));
      expect(Uri.parse(requests.last.url).queryParameters['assign_type'], 'person_id');
      expect(jsonDecode(requests.last.body)['segment_ids'], ['a']);
    });
  }
  test('old server bulk fallback preserves explicit selection and stale status', () async {
    final requests = <ApiRequest>[];
    final result = await assignRecordingSpeakers(
        'c1',
        [
          {
            'conversation_id': 'c1',
            'segment_ids': ['a']
          }
        ],
        personId: 'maya',
        wholeRecording: false, send: (request) async {
      requests.add(request);
      return requests.length == 1 ? http.Response('{}', 404) : http.Response('{}', 409);
    });
    expect(requests.last.url, endsWith('/conversations/c1/segments/assign-bulk'));
    expect((result as ApiFailure<int>).problem.statusCode, 409);
  });
  for (final response in [
    {'applied_count': 1},
    {'applied_count': 1, 'conversations': null},
    {
      'applied_count': 1,
      'conversations': [
        {'conversation_id': 'c1'}
      ]
    },
  ]) {
    test('malformed member outcomes are a decode failure: $response', () async {
      final result = await assignRecordingSpeakers(
          'c1',
          [
            {
              'conversation_id': 'c1',
              'segment_ids': ['a']
            }
          ],
          personId: 'maya',
          wholeRecording: false,
          send: (_) async => http.Response(jsonEncode(response), 200));
      expect((result as ApiFailure<int>).problem.kind, ApiProblemKind.decode);
    });
  }
  test('all stale member outcomes show stale feedback rather than claiming partial success', () async {
    await expectLater(
        assignRecordingSpeakers(
            'c1',
            [
              {
                'conversation_id': 'c1',
                'segment_ids': ['a']
              }
            ],
            personId: 'maya',
            wholeRecording: false,
            send: (_) async => http.Response(
                jsonEncode({
                  'applied_count': 0,
                  'conversations': [
                    {'conversation_id': 'c1', 'applied_count': 0, 'error': 'stale_speaker'}
                  ]
                }),
                200)),
        throwsA(isA<StaleSpeakerException>()));
  });
  test('per-member outcomes survive HTTP decoding', () async {
    await expectLater(
        assignRecordingSpeakers(
            'c1',
            [
              {
                'conversation_id': 'c1',
                'segment_ids': ['a']
              },
              {
                'conversation_id': 'c2',
                'segment_ids': ['b']
              }
            ],
            personId: 'maya',
            wholeRecording: false,
            send: (_) async => http.Response(
                jsonEncode({
                  'applied_count': 1,
                  'conversations': [
                    {'conversation_id': 'c1', 'applied_count': 1},
                    {'conversation_id': 'c2', 'applied_count': 0, 'error': 'stale_speaker'}
                  ]
                }),
                200)),
        throwsA(isA<PartialSpeakerAssignmentException>()
            .having((e) => e.succeeded, 'succeeded', {'c1'}).having((e) => e.failed, 'failed', {'c2'})));
  });
}
