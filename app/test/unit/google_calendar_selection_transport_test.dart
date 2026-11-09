import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api/google_calendars.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/integrations/google_calendar_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class _Env implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://api.omi.me/';
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() => Env.init(_Env()));

  test('malformed catalogs and access denial are typed failures, never an empty selection', () async {
    SharedPreferences.setMockInitialValues({'uid': 'owner'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    final previous = HttpOverrides.current;
    HttpOverrides.global = null;
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    var status = 200;
    server.listen((request) async {
      await request.drain<void>();
      request.response.statusCode = status;
      request.response.headers.contentType = ContentType.json;
      request.response.write(status == 200 ? '{"account_id":null}' : '{"detail":"access_denied"}');
      await request.response.close();
    });
    Env.overrideApiBaseUrl('http://127.0.0.1:${server.port}/');
    try {
      final owner = GoogleCalendarService.meetingCacheOwner;
      await expectLater(
        googleCalendarSelection(owner),
        throwsA(isA<GoogleCalendarSelectionFailure>().having((e) => e.problem.kind, 'kind', ApiProblemKind.decode)),
      );
      status = 403;
      await expectLater(
        googleCalendarSelection(owner),
        throwsA(isA<GoogleCalendarSelectionFailure>().having((e) => e.problem.kind, 'kind', ApiProblemKind.forbidden)),
      );
    } finally {
      Env.clearApiBaseUrlOverrideForTesting();
      HttpOverrides.global = previous;
      await server.close(force: true);
    }
  });

  test('real HTTP catalog/save round trip invalidates prior meeting reads and refuses a stale owner', () async {
    SharedPreferences.setMockInitialValues({'uid': 'owner'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    final previous = HttpOverrides.current;
    HttpOverrides.global = null;
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final calls = <String>[];
    Map<String, dynamic>? written;
    server.listen((request) async {
      calls.add('${request.method} ${request.uri}');
      final body = await utf8.decoder.bind(request).join();
      if (request.method == 'PUT') written = jsonDecode(body) as Map<String, dynamic>;
      request.response.headers.contentType = ContentType.json;
      request.response.write(jsonEncode({
        'account_id': 'personal@example.test',
        'calendars': [
          {'id': 'personal@example.test', 'name': 'Personal', 'primary': true, 'available': true},
          {'id': 'team', 'name': 'Team', 'primary': false, 'available': true},
        ],
        'selected_ids': written?['selected_ids'] ?? ['personal@example.test'],
        'write_calendar_id': 'primary',
      }));
      await request.response.close();
    });
    Env.overrideApiBaseUrl('http://127.0.0.1:${server.port}/');
    try {
      final owner = GoogleCalendarService.meetingCacheOwner;
      final catalog = await googleCalendarSelection(owner);
      expect(catalog.selectedIds, {'personal@example.test'});
      final saved = await googleCalendarSelection(owner,
          selection: GoogleCalendarSelection(
            catalog.accountId,
            catalog.calendars,
            {'team'},
          ));
      expect(saved.selectedIds, {'team'});
      expect(written, {
        'account_id': 'personal@example.test',
        'selected_ids': ['team']
      });
      expect(GoogleCalendarService.meetingCacheOwner, isNot(owner));
      expect(GoogleCalendarService.knownMeetings.value.windows, isEmpty);
      await expectLater(googleCalendarSelection(owner, selection: saved), throwsStateError);
      expect(calls, ['GET /v1/calendar/google/calendars', 'PUT /v1/calendar/google/calendars']);
    } finally {
      Env.clearApiBaseUrlOverrideForTesting();
      HttpOverrides.global = previous;
      await server.close(force: true);
    }
  });

  test('a catalog response for a replaced account is never published', () async {
    SharedPreferences.setMockInitialValues({'uid': 'owner'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    final previous = HttpOverrides.current;
    HttpOverrides.global = null;
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final arrived = Completer<void>();
    final release = Completer<void>();
    server.listen((request) async {
      arrived.complete();
      await release.future;
      request.response.headers.contentType = ContentType.json;
      request.response.write('{"account_id":"old","calendars":[],"selected_ids":["old"]}');
      await request.response.close();
    });
    Env.overrideApiBaseUrl('http://127.0.0.1:${server.port}/');
    try {
      final request = googleCalendarSelection(GoogleCalendarService.meetingCacheOwner);
      final refused = expectLater(request, throwsStateError);
      await arrived.future;
      SharedPreferencesUtil().uid = 'replacement';
      release.complete();
      await refused;
    } finally {
      Env.clearApiBaseUrlOverrideForTesting();
      HttpOverrides.global = previous;
      await server.close(force: true);
    }
  });
}
