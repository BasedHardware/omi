import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/gen/home_feed_wire.g.dart' as feed_wire;
import 'package:omi/backend/schema/home_feed.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/home_feed_provider.dart';

Map<String, dynamic> _conversationJson({Map<String, dynamic> extra = const {}}) => {
      'id': 'c1',
      'created_at': '2026-11-16T08:00:00Z',
      'started_at': '2026-11-16T08:00:00Z',
      'finished_at': null,
      'structured': {'title': 'Planning the launch', 'overview': '', 'emoji': '🚀', 'category': 'work'},
      'transcript_segments': <Object>[],
      'status': 'in_progress',
      ...extra,
    };

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('v3 conversation fields', () {
    test('absent on an older document', () {
      expect(ServerConversation.fromJson(_conversationJson()).v3, isNull);
    });

    test('read from the wire and written back', () {
      final c = ServerConversation.fromJson(_conversationJson(extra: {
        'kind': 'conversation',
        'home_hidden': false,
        'tile_state': 'writing',
        'title_locked': true,
        'recording_pieces': [
          {'recording_id': 'r1', 'audio_file_id': 'a1', 'start': 12.5, 'end': 340.0},
        ],
        'summary_covers_through': '2026-11-16T08:30:00Z',
      }));
      final v3 = c.v3!;
      expect(v3.kind, 'conversation');
      expect(v3.tileState, ConversationTileState.writing);
      expect(v3.titleLocked, isTrue);
      expect(v3.recordingPieces, hasLength(1));
      expect(v3.recordingPieces.single.end, 340.0);
      expect(v3.summaryCoversThrough, DateTime.utc(2026, 11, 16, 8, 30));
      final again = ServerConversation.fromJson(c.toJson()).v3!;
      expect(again.tileState, ConversationTileState.writing);
      expect(again.recordingPieces.single.recordingId, 'r1');
    });

    test('the piece reader drops a malformed piece (the generated wire decoder rejects it first)', () {
      expect(RecordingPiece.fromJson({'recording_id': 'bad'}), isNull);
      expect(RecordingPiece.fromJson({'recording_id': 'r', 'audio_file_id': 'a', 'start': 5, 'end': 1}), isNull);
    });

    test('the compact live row the server sends decodes', () {
      final read = ConversationsLiveRead.fromGeneratedWireJson({
        'v3': true,
        'conversation': {
          'id': 'c-live',
          'structured': {'title': 'Standup', 'emoji': '🗣️'},
          'started_at': '2026-11-16T09:00:00Z',
          'created_at': '2026-11-16T09:00:00Z',
          'finished_at': null,
          'status': 'in_progress',
          'tile_state': 'live',
        },
      });
      expect(read.v3, isTrue);
      expect(read.conversation?.id, 'c-live');
      expect(read.conversation?.structured.title, 'Standup');
      expect(read.conversation?.v3?.tileState, ConversationTileState.live);
      expect(read.conversation?.transcriptSegments, isEmpty);
    });

    test('a failed conversation decodes through the generated wire type', () {
      final read = ConversationsLiveRead.fromGeneratedWireJson({
        'v3': true,
        'conversation': {
          'id': 'c-failed',
          'structured': {'title': 'Planning', 'emoji': '🗓️'},
          'started_at': '2026-11-16T09:00:00Z',
          'created_at': '2026-11-16T09:00:00Z',
          'finished_at': '2026-11-16T09:20:00Z',
          'status': 'completed',
          'tile_state': 'failed',
        },
      });
      expect(read.conversation?.v3?.tileState, ConversationTileState.failed);
    });

    test('an unreadable live row still answers the switch', () {
      final read = ConversationsLiveRead.fromGeneratedWireJson({
        'v3': true,
        'conversation': {'id': 'c-live', 'status': 'in_progress'},
      });
      expect(read.v3, isTrue);
      expect(read.conversation, isNull);
    });

    test('every tile state the server sends parses, failed included', () {
      expect(ConversationTileState.parse('failed'), ConversationTileState.failed);
      expect(ConversationTileState.parse('done'), ConversationTileState.done);
    });

    test('an unknown tile state reads as none', () {
      expect(ConversationTileState.parse('sparkling'), isNull);
    });
  });

  group('summary stream frames', () {
    String done(Map<String, dynamic> json) => 'done: ${base64.encode(utf8.encode(jsonEncode(json)))}';

    test('a section, with escaped newlines', () {
      final event = parseSummaryFrame('data: ## Plan__CRLF__- ship it');
      expect(event, isA<SummarySection>());
      expect((event as SummarySection).markdown, '## Plan\n- ship it');
    });

    test('done carries the stored summary', () {
      final event = parseSummaryFrame(done({
        'structured': {'title': 'Planning', 'overview': 'We planned.', 'emoji': '🚀', 'category': 'work'},
        'summary_covers_through': '2026-11-16T08:30:00Z',
      }));
      expect(event, isA<SummaryDone>());
      expect((event as SummaryDone).structured.overview, 'We planned.');
      expect(event.coversThrough, DateTime.utc(2026, 11, 16, 8, 30));
    });

    test('a malformed done frame fails instead of throwing', () {
      expect(parseSummaryFrame('done: not-base64!'), isA<SummaryFailed>());
      expect(parseSummaryFrame(done({'summary_covers_through': null})), isA<SummaryFailed>());
    });

    test('errors, the in-progress signal and keep-alives', () {
      expect(parseSummaryFrame('error: {"detail": "summary_in_progress"}'), isA<SummaryInProgress>());
      final failed = parseSummaryFrame('error: {"detail": "quota"}');
      expect(failed, isA<SummaryFailed>());
      expect((failed as SummaryFailed).detail, 'quota');
      expect(parseSummaryFrame(': ping'), isNull);
      expect(parseSummaryFrame('   '), isNull);
    });
  });

  group('ConversationsV3Provider', () {
    ApiResult<ConversationsLiveRead> live(bool v3, {Map<String, dynamic>? conversation}) =>
        ApiSuccess(ConversationsLiveRead.fromGeneratedWireJson({'v3': v3, 'conversation': conversation}));

    test('unknown until the server answers, and legacy reads wait for the answer', () async {
      final provider = ConversationsV3Provider(fetchLive: () async => live(false), uid: () => 'u1', cached: '');
      expect(provider.v3, isFalse);
      expect(provider.resolved, isFalse);
      expect(provider.suppressesLegacy, isTrue);
      await provider.refresh();
      expect(provider.resolved, isTrue);
      expect(provider.suppressesLegacy, isFalse);
      await Future<void>.delayed(Duration.zero);
      expect(SharedPreferencesUtil().getString('conversationsV3Answer'), 'u1:0');
      final next = ConversationsV3Provider(fetchLive: () async => live(true), uid: () => 'u1');
      expect(next.resolved, isTrue, reason: 'a remembered "no" is an answer too');
      expect(next.suppressesLegacy, isFalse);
    });

    test('a server error as the first answer runs today\'s Home; offline stays unknown', () async {
      ApiResult<ConversationsLiveRead> result = const ApiFailure(ApiProblem(ApiProblemKind.transport));
      final provider = ConversationsV3Provider(fetchLive: () async => result, uid: () => 'u1', cached: '');
      await provider.refresh();
      expect(provider.resolved, isFalse);
      result = const ApiFailure(ApiProblem(ApiProblemKind.server, statusCode: 503));
      await provider.refresh();
      expect(provider.resolved, isTrue);
      expect(provider.v3, isFalse);
      await Future<void>.delayed(Duration.zero);
      expect(SharedPreferencesUtil().getString('conversationsV3Answer'), isEmpty, reason: 'not remembered');
    });

    test('an account switch mid-read leaves one read in flight', () async {
      var uid = 'u1';
      var calls = 0;
      final gates = <Completer<ApiResult<ConversationsLiveRead>>>[];
      final provider = ConversationsV3Provider(
        fetchLive: () {
          calls++;
          final gate = Completer<ApiResult<ConversationsLiveRead>>();
          gates.add(gate);
          return gate.future;
        },
        uid: () => uid,
        cached: '',
      );
      final first = provider.refresh();
      uid = 'u2';
      final second = provider.refresh();
      gates[0].complete(live(true));
      await first;
      final third = provider.refresh();
      expect(calls, 2, reason: 'the old read must not clear the new read\'s slot');
      gates[1].complete(live(true));
      await Future.wait([second, third]);
      expect(provider.v3, isTrue);
    });

    test('on with a live conversation, and remembered for this account only', () async {
      final provider = ConversationsV3Provider(
        fetchLive: () async => live(true, conversation: _conversationJson(extra: {'tile_state': 'live'})),
        uid: () => 'u1',
        cached: '',
      );
      await provider.refresh();
      expect(provider.v3, isTrue);
      expect(provider.live?.v3?.tileState, ConversationTileState.live);
      await Future<void>.delayed(Duration.zero);
      expect(SharedPreferencesUtil().getString('conversationsV3Answer'), 'u1:1');

      final sameAccount = ConversationsV3Provider(fetchLive: () async => live(true), uid: () => 'u1');
      expect(sameAccount.v3, isTrue, reason: 'a cold start opens on the remembered Home');
      final otherAccount = ConversationsV3Provider(fetchLive: () async => live(true), uid: () => 'u2');
      expect(otherAccount.v3, isFalse);
    });

    test('a 404 is an older server; other failures keep the last answer', () async {
      var result = live(true);
      final provider = ConversationsV3Provider(fetchLive: () async => result, uid: () => 'u1', cached: '');
      await provider.refresh();
      expect(provider.v3, isTrue);
      result = const ApiFailure(ApiProblem(ApiProblemKind.transport));
      await provider.refresh();
      expect(provider.v3, isTrue);
      result = const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404));
      await provider.refresh();
      expect(provider.v3, isFalse);
    });

    test('ignores a late answer for a previous account', () async {
      var uid = 'u1';
      final provider = ConversationsV3Provider(
        fetchLive: () async {
          uid = 'u2';
          return live(true);
        },
        uid: () => uid,
        cached: '',
      );
      await provider.refresh();
      expect(provider.v3, isFalse);
    });

    test('watching polls; unwatching stops', () async {
      var calls = 0;
      final provider = ConversationsV3Provider(
        fetchLive: () async {
          calls++;
          return live(true);
        },
        uid: () => 'u1',
        cached: '',
      );
      provider.watch();
      provider.watch(); // a second watcher shares the poll
      await Future<void>.delayed(Duration.zero);
      expect(calls, 1);
      expect(provider.polling, isTrue);
      provider.unwatch();
      expect(provider.polling, isTrue, reason: 'one watcher left');
      provider.unwatch();
      expect(provider.polling, isFalse);
      provider.dispose();
    });
  });

  group('a v3 account makes no episode or feed calls', () {
    test('episode reads are skipped and the Home overlay is complete', () async {
      var calls = 0;
      final episodes = EpisodeProvider(
        fetchLive: () async {
          calls++;
          return const ApiSuccess(EpisodeRead(enabled: true));
        },
        fetchPage: (from, to, {cursor}) async {
          calls++;
          return const ApiSuccess(EpisodePageRead(enabled: true));
        },
        lookup: (_) async {
          calls++;
          return const ApiSuccess(EpisodeRead.disabled);
        },
      )..suppressed = () => true;
      await episodes.refreshLive();
      expect(await episodes.refreshHome(DateTime(2026, 11, 1), DateTime(2026, 11, 17), bootstrap: true), isTrue);
      expect(await episodes.episodeFor('c1'), isNull);
      await episodes.recoverPrevious('c1');
      expect(calls, 0);
      expect(episodes.enabled, isFalse);
      episodes.dispose();
    });

    test('the Home feed stays inactive', () async {
      var calls = 0;
      final feed = HomeFeedProvider(
        fetch: ({cursor}) async {
          calls++;
          return const ApiSuccess(HomeFeedPage(items: [], nextCursor: null, hasMore: false, truncated: false));
        },
        owner: () => 'u1',
      )..suppressed = () => true;
      feed.setActive(true);
      await feed.start();
      await feed.refresh();
      expect(calls, 0);
      feed.dispose();
    });
  });

  group('wire decoders', _wireDecoderContracts);
}

/// Synthetic additive-wire and capture-identity decoder contracts (current source, not a released build).
void _wireDecoderContracts() {
  final base = <String, dynamic>{
    'id': 'synthetic-conversation',
    'created_at': '2026-11-16T10:00:00Z',
    'started_at': '2026-11-16T10:00:00Z',
    'finished_at': '2026-11-16T10:05:00Z',
    'source': 'omi',
    'status': 'completed',
    'structured': {'title': 'Planning the next visit', 'overview': 'A synthetic summary', 'emoji': '🌳'},
    'transcript_segments': [
      {'text': 'Synthetic speech inside this conversation.', 'start': 0.0, 'end': 4.0, 'is_user': true}
    ],
  };
  test('additive v3 fields preserve the existing conversation decoder', () {
    final row = ServerConversation.fromJson({
      ...base,
      'kind': 'conversation',
      'home_hidden': false,
      'tile_state': 'done',
      'title_locked': true,
      'recording_pieces': [
        {'recording_id': 'r', 'audio_file_id': 'f', 'start': 12.5, 'end': 25.0}
      ],
      'summary_covers_through': '2026-11-16T10:05:00Z',
    });
    expect(row.id, base['id']);
    expect(row.structured.title, 'Planning the next visit');
    expect(row.transcriptSegments.single.text, 'Synthetic speech inside this conversation.');
    expect(row.isHiddenFromDefaultList, false);
  });
  test('capture socket payload preserves recording identity and donor bridge', () {
    final live = ServerConversation.fromJson({...base, 'id': 'recording', 'status': 'in_progress', 'recording': true});
    expect(live.id, 'recording');
    final completed = ServerConversation.fromJson({...base, 'id': 'recording', 'sync_merged_into': 'covering'});
    expect(completed.id, 'recording');
    expect(completed.isMergedDonor, true);
  });
  test('v3 Home uses the existing closed kind vocabulary', () {
    final card = feed_wire.GeneratedHomeFeedCard.fromJson({
      'id': 'c',
      'kind': 'conversation',
      'detail_id': 'c',
      'sort_at': base['created_at'],
      'status': 'completed',
      'revision': 'synthetic',
    });
    expect(card.kind, 'conversation');
  });
  test('compact live row decodes with a nullable finished_at key', () {
    final row = ServerConversation.fromJson({
      'id': 'live',
      'created_at': base['created_at'],
      'started_at': base['started_at'],
      'finished_at': null,
      'status': 'in_progress',
      'tile_state': 'live',
      'structured': {'title': 'A plan', 'emoji': '🌳'},
    });
    expect(row.id, 'live');
    expect(row.finishedAt, isNull);
  });
  test('pending v3 aliases keep playback and export polling without a source URL', () {
    final response = AudioUrlsResponse.fromJson({
      'audio_files': [
        {'id': 'alias', 'status': 'pending', 'signed_url': null, 'duration': 10}
      ],
      'conversation_audio': {'status': 'pending', 'signed_url': null, 'spans': []},
      'poll_after_ms': 5000,
    });
    expect(response.files, isNotEmpty);
    expect(response.hasPending, true);
    expect(response.playbackReady, false);
    expect(response.files.single.signedUrl, isNull);
  });
}
