import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api/episodes.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/episode_provider.dart';

import '../helpers/home_fixture_env.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() => Env.init(HomeFixtureEnv()));
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('full detail API decodes gist, classifier and provenance without Home history', () async {
    final at = DateTime.utc(2026, 11, 9).toIso8601String();
    final result = await api.getEpisode('episode/1', send: (request) async {
      expect(request.url, 'http://127.0.0.1:1/v1/episodes/episode%2F1');
      expect(request.method, 'GET');
      return http.Response(
          jsonEncode({
            'id': 'episode/1',
            'status': 'closed',
            'started_at': at,
            'last_activity_at': at,
            'members': [
              {'id': 'ready', 'title': 'Plans', 'overview': 'Reuse the trays.', 'home_step': 'ready', 'started_at': at},
              {
                'id': 'noise',
                'title': 'Recording',
                'home_step': 'noise',
                'title_provenance': 'server_minimum',
                'started_at': at
              },
              {'id': 'legacy', 'started_at': at},
            ]
          }),
          200);
    });
    final episode = (result as ApiSuccess<Episode>).data;
    expect(episode.members[0].structured.overview, 'Reuse the trays.');
    expect(episode.members[0].homeStep, 'ready');
    expect(episode.members[1].homeStep, 'noise');
    expect(episode.members[1].structured.titleProvenance, 'server_minimum');
    expect(episode.members[2].homeStep, isNull);
    expect(episode.members[2].structured.overview, isEmpty);
  });

  test('full detail response is ignored after account changes', () async {
    SharedPreferencesUtil().uid = 'account-a';
    final pending = Completer<ApiResult<Episode>>();
    final episodes = EpisodeProvider(fetchDetail: (_) => pending.future);
    addTearDown(episodes.dispose);
    final reading = episodes.detailFor('episode-1');
    SharedPreferencesUtil().uid = 'account-b';
    pending.complete(
        ApiSuccess(Episode(id: 'episode-1', live: false, startedAt: DateTime(2026), lastActivityAt: DateTime(2026))));
    final result = await reading;
    expect(result, isA<ApiFailure<Episode>>());
    expect((result as ApiFailure).problem.kind, ApiProblemKind.authTerminal);
  });
}
