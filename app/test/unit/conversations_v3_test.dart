import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations_v3.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/backend/schema/episode.dart';
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
          {'recording_id': 'bad'},
        ],
        'summary_covers_through': '2026-11-16T08:30:00Z',
      }));
      final v3 = c.v3!;
      expect(v3.kind, 'conversation');
      expect(v3.tileState, ConversationTileState.writing);
      expect(v3.titleLocked, isTrue);
      expect(v3.recordingPieces, hasLength(1), reason: 'a malformed piece is dropped, not fatal');
      expect(v3.recordingPieces.single.end, 340.0);
      expect(v3.summaryCoversThrough, DateTime.utc(2026, 11, 16, 8, 30));
      final again = ServerConversation.fromJson(c.toJson()).v3!;
      expect(again.tileState, ConversationTileState.writing);
      expect(again.recordingPieces.single.recordingId, 'r1');
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
        ApiSuccess(ConversationsLiveRead.fromJson({'v3': v3, 'conversation': conversation}));

    test('off until the server says otherwise', () {
      final provider = ConversationsV3Provider(fetchLive: () async => live(false), uid: () => 'u1', cachedUid: '');
      expect(provider.v3, isFalse);
      expect(provider.live, isNull);
    });

    test('on with a live conversation, and remembered for this account only', () async {
      final provider = ConversationsV3Provider(
        fetchLive: () async => live(true, conversation: _conversationJson(extra: {'tile_state': 'live'})),
        uid: () => 'u1',
        cachedUid: '',
      );
      await provider.refresh();
      expect(provider.v3, isTrue);
      expect(provider.live?.v3?.tileState, ConversationTileState.live);
      await Future<void>.delayed(Duration.zero);
      expect(SharedPreferencesUtil().getString('conversationsV3Uid'), 'u1');

      final sameAccount = ConversationsV3Provider(fetchLive: () async => live(true), uid: () => 'u1');
      expect(sameAccount.v3, isTrue, reason: 'a cold start opens on the remembered Home');
      final otherAccount = ConversationsV3Provider(fetchLive: () async => live(true), uid: () => 'u2');
      expect(otherAccount.v3, isFalse);
    });

    test('a 404 is an older server; other failures keep the last answer', () async {
      var result = live(true);
      final provider = ConversationsV3Provider(fetchLive: () async => result, uid: () => 'u1', cachedUid: '');
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
        cachedUid: '',
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
        cachedUid: '',
      );
      provider.watch();
      await Future<void>.delayed(Duration.zero);
      expect(calls, 1);
      provider.unwatch();
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
}
