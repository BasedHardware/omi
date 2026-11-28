import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/env/env.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/transcription_pending_conversations.dart';

import '../helpers/home_fixture_env.dart';
import '../helpers/summary_fixtures.dart';

/// A provider whose crash reporter itself fails.
class _ThrowingReporterProvider extends ConversationDetailProvider {
  _ThrowingReporterProvider({super.reprocess});

  int reports = 0;

  @override
  Future<void> reportReprocessCrash(Object error, StackTrace stackTrace, ServerConversation target) async {
    reports++;
    throw StateError('crash reporter unavailable');
  }
}

http.Response _json(int status, Object body, {Map<String, String> headers = const {}}) =>
    http.Response(jsonEncode(body), status, headers: {'content-type': 'application/json', ...headers});

void main() {
  setUpAll(() => Env.init(HomeFixtureEnv()));
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('reprocessResultFromResponse', () {
    test('200 decodes the conversation', () {
      final result = reprocessResultFromResponse(_json(200, summaryConversation(overview: 'Done').toJson()));
      expect(result, isA<ReprocessSuccess>());
      expect(result.conversation!.structured.overview, 'Done');
    });

    test('200 without the speaker receipt the request required is a failure', () {
      final result = reprocessResultFromResponse(
        _json(200, summaryConversation(overview: 'Done').toJson()),
        requireSpeakerReceipt: true,
      );
      expect(result, isA<ReprocessFailed>());
    });

    test('200 with an undecodable body is a failure, not a throw', () {
      expect(reprocessResultFromResponse(http.Response('not json', 200)), isA<ReprocessFailed>());
    });

    test('200 back in Home step transcribing is the in-window wait, with its copy, receipt or not', () {
      final waiting = {
        ...summaryConversation().toJson(),
        'status': 'processing',
        'home_step': 'transcribing',
      };
      for (final requireSpeakerReceipt in [false, true]) {
        final result = reprocessResultFromResponse(_json(200, waiting), requireSpeakerReceipt: requireSpeakerReceipt);
        expect(result, isA<ReprocessTranscriptionPending>());
        expect(result.conversation!.homeStep, 'transcribing');
        expect(result.conversation!.status, ConversationStatus.processing);
      }
    });

    test('409 conversation_processing_in_progress is busy', () {
      final result = reprocessResultFromResponse(_json(409, {
        'detail': {'code': 'conversation_processing_in_progress', 'message': 'Already processing'},
      }));
      expect(result, isA<ReprocessBusy>());
    });

    test('409 transcription_pending is waiting for transcription, not a failure', () {
      final result = reprocessResultFromResponse(_json(409, {
        'detail': {
          'code': 'transcription_pending',
          'message': 'Audio is awaiting transcription; summary retry cannot transcribe it',
        },
      }));
      expect(result, isA<ReprocessTranscriptionPending>());
    });

    test('409 with a string detail is the app selection failing, not busy', () {
      final result = reprocessResultFromResponse(
        _json(409, {'detail': 'App must be enabled before it can summarize a conversation'}),
      );
      expect(result, isA<ReprocessFailed>());
      expect((result as ReprocessFailed).statusCode, 409);
    });

    test('429 is the rate limit and keeps Retry-After', () {
      final result = reprocessResultFromResponse(_json(429, {'detail': 'slow down'}, headers: {'retry-after': '120'}));
      expect(result, isA<ReprocessRateLimited>());
      expect((result as ReprocessRateLimited).retryAfter, const Duration(minutes: 2));
    });

    for (final (wireCode, code) in [
      ('byok_quota', ReprocessProviderAccountCode.quota),
      ('byok_rate_limit', ReprocessProviderAccountCode.rateLimit),
      ('byok_invalid_key', ReprocessProviderAccountCode.invalidKey),
    ]) {
      test('429 $wireCode preserves the provider account code without a message', () {
        final result = reprocessResultFromResponse(_json(429, {
          'detail': {'code': wireCode},
        }));
        expect(result, isA<ReprocessProviderAccountFailure>().having((result) => result.code, 'code', code));
      });
    }

    test('502 app_result_failed and 500 are failures', () {
      expect(
        reprocessResultFromResponse(_json(502, {
          'detail': {'code': 'app_result_failed', 'message': 'no content', 'failure_class': 'empty_model_output'},
        })),
        isA<ReprocessFailed>(),
      );
      expect(reprocessResultFromResponse(http.Response('', 500)), isA<ReprocessFailed>());
    });
  });

  test('reprocess repeats a typed 503 once using Retry-After and the same template', () async {
    final urls = <String>[];
    final delays = <Duration>[];
    final result = await reProcessConversationServer(
      'conv-summary',
      appId: 'pg',
      send: (url) async {
        urls.add(url);
        return _json(503, {
          'detail': {'code': 'conversation_processing_retryable'},
        }, headers: {
          'retry-after': '4'
        });
      },
      waitBeforeRetry: (delay) async => delays.add(delay),
    );
    expect(urls, hasLength(2));
    expect(urls.first, endsWith('/conv-summary/reprocess?app_id=pg'));
    expect(urls.last, urls.first);
    expect(delays, [const Duration(seconds: 4)]);
    expect(result, isA<ReprocessFailed>().having((result) => result.statusCode, 'statusCode', 503));
  });

  test('reprocess does not automatically repeat an untyped 503 or a 502', () async {
    for (final status in [502, 503]) {
      var sends = 0;
      final result = await reProcessConversationServer(
        'conv-summary',
        appId: 'pg',
        send: (_) async {
          sends++;
          return http.Response('', status);
        },
        waitBeforeRetry: (_) async => fail('Only a typed processing 503 can be repeated'),
      );
      expect(sends, 1);
      expect(result, isA<ReprocessFailed>().having((result) => result.statusCode, 'statusCode', status));
    }
  });

  group('reprocessConversation outcome', () {
    Future<(ConversationDetailProvider, bool)> run(ReprocessResult result, {String? appId}) async {
      final provider = summaryProvider(
        summaryConversation(),
        reprocess: (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) async => result,
        catalog: [summaryApp('pg', 'Paul Graham')],
      );
      addTearDown(provider.dispose);
      final ok = await provider.reprocessConversation(appId: appId);
      return (provider, ok);
    }

    test('409 busy becomes a busy failure for this conversation', () async {
      final (provider, ok) = await run(const ReprocessBusy());
      expect(ok, isFalse);
      expect(provider.summaryFailure!.kind, SummaryFailureKind.busy);
      expect(provider.summaryFailure!.conversationId, 'conv-summary');
      expect(provider.loadingReprocessConversation, isFalse);
    });

    test('409 transcription_pending is a waiting status, not an error, and marks the conversation', () async {
      TranscriptionPendingConversations.reset();
      addTearDown(TranscriptionPendingConversations.reset);
      final errors = <String>[];
      final infos = <String>[];
      final provider = summaryProvider(
        summaryConversation(),
        reprocess: (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) async =>
            const ReprocessTranscriptionPending(),
      );
      addTearDown(provider.dispose);
      provider.addListener(() {
        if (provider.error case final e?) errors.add(e);
        if (provider.info case final i?) infos.add(i);
      });
      final ok = await provider.reprocessConversation();
      expect(ok, isFalse);
      expect(provider.summaryFailure!.kind, SummaryFailureKind.transcriptionPending);
      expect(provider.loadingReprocessConversation, isFalse);
      expect(TranscriptionPendingConversations.contains('conv-summary'), isTrue);
      expect(errors, isNot(contains('REPROCESS_FAILED')));
      expect(infos, contains('REPROCESS_TRANSCRIPTION_PENDING'));
    });

    test('a 200 in-window wait applies the server copy and is a waiting status, not an error', () async {
      TranscriptionPendingConversations.reset();
      addTearDown(TranscriptionPendingConversations.reset);
      final errors = <String>[];
      final infos = <String>[];
      final waiting = ServerConversation.fromJson({
        ...summaryConversation().toJson(),
        'status': 'processing',
        'home_step': 'transcribing',
      });
      final provider = summaryProvider(
        summaryConversation(),
        reprocess: (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) async =>
            ReprocessTranscriptionPending(waiting),
      );
      addTearDown(provider.dispose);
      provider.addListener(() {
        if (provider.error case final e?) errors.add(e);
        if (provider.info case final i?) infos.add(i);
      });
      final ok = await provider.reprocessConversation();
      expect(ok, isFalse);
      expect(provider.conversation.status, ConversationStatus.processing);
      expect(provider.conversation.homeStep, 'transcribing');
      expect(provider.summaryFailure!.kind, SummaryFailureKind.transcriptionPending);
      expect(TranscriptionPendingConversations.contains('conv-summary'), isFalse);
      expect(errors, isNot(contains('REPROCESS_FAILED')));
      expect(infos, contains('REPROCESS_TRANSCRIPTION_PENDING'));
    });

    test('429 becomes the rate-limit failure', () async {
      final (provider, ok) = await run(const ReprocessRateLimited());
      expect(ok, isFalse);
      expect(provider.summaryFailure!.kind, SummaryFailureKind.rateLimited);
    });

    test('a 200 that still has no summary is a failure, not "Conversation updated"', () async {
      final (provider, ok) = await run(ReprocessSuccess(summaryConversation()));
      expect(ok, isFalse);
      expect(provider.summaryFailure!.kind, SummaryFailureKind.generic);
      expect(provider.reprocessedConversationId, isNull);
    });

    test('an Omi request answered 200 with an empty overview and a stale template result is a failure', () async {
      // summary-v2 F1: a busy echo from an older backend carries the stored row; a template result
      // already on it is not the Omi summary that was asked for.
      final (provider, ok) = await run(ReprocessSuccess(summaryConversation(
        appResults: [AppResponse('Stale Paul Graham essay', appId: 'pg')],
      )));
      expect(ok, isFalse);
      expect(provider.summaryFailure!.kind, SummaryFailureKind.generic);
      expect(provider.reprocessedConversationId, isNull);
    });

    test('a 200 without the requested template result is that template failing', () async {
      final (provider, ok) = await run(ReprocessSuccess(summaryConversation(overview: 'Omi wrote this')), appId: 'pg');
      expect(ok, isFalse);
      expect(provider.summaryFailure!.kind, SummaryFailureKind.template);
      expect(provider.summaryFailure!.appId, 'pg');
      expect(provider.lastFailedReprocessAppId, 'pg');
    });

    test('a failed template request (502) is a template failure', () async {
      final (provider, _) = await run(const ReprocessFailed(statusCode: 502), appId: 'pg');
      expect(provider.summaryFailure!.kind, SummaryFailureKind.template);
    });

    test('success shows the summary that was asked for, even when another template result comes first', () async {
      final (provider, ok) = await run(ReprocessSuccess(summaryConversation(
        overview: 'Omi overview',
        appResults: [AppResponse('Paul Graham essay', appId: 'pg')],
      )));
      expect(ok, isTrue);
      expect(provider.summaryFailure, isNull);
      expect(provider.getSummarySelection().appId, 'pg', reason: 'the stored order still leads with the app');
      expect(provider.getDisplayedSummarySelection().content, 'Omi overview');
    });

    test('a throwing reprocess settles the page even when crash reporting throws too', () async {
      final conversation = summaryConversation();
      final provider = _ThrowingReporterProvider(
        reprocess: (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) async =>
            throw StateError('transport'),
      )
        ..selectedDate = conversationLocalDayKey(conversation.startedAt ?? conversation.createdAt)
        ..setCachedConversation(conversation);
      addTearDown(provider.dispose);

      expect(await provider.reprocessConversation(appId: 'pg'), isFalse);
      expect(provider.reports, 1);
      expect(provider.loadingReprocessConversation, isFalse);
      expect(provider.isReprocessingOpenConversation, isFalse);
      expect(provider.summaryFailure!.kind, SummaryFailureKind.template);
      expect(provider.lastFailedReprocessAppId, 'pg');
    });

    test('forceOmi reaches the request only for Omi; a template request never forces Omi', () async {
      final seen = <(String?, bool)>[];
      final provider = summaryProvider(
        summaryConversation(),
        reprocess: (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) async {
          seen.add((appId, forceOmi));
          return ReprocessSuccess(summaryConversation(overview: 'Done'));
        },
      );
      addTearDown(provider.dispose);
      await provider.reprocessConversation(forceOmi: true);
      await provider.reprocessConversation(appId: 'pg', forceOmi: true);
      await provider.reprocessConversation();
      expect(seen, [(null, true), ('pg', false), (null, false)]);
    });

    test('a second request while one runs does nothing', () async {
      final gate = Completer<ReprocessResult>();
      var calls = 0;
      final provider = summaryProvider(
        summaryConversation(),
        reprocess: (id, {appId, requireSpeakerReceipt = false, forceOmi = false}) {
          calls++;
          return gate.future;
        },
      );
      addTearDown(provider.dispose);
      final first = provider.reprocessConversation();
      expect(await provider.reprocessConversation(appId: 'pg'), isFalse);
      expect(calls, 1);
      expect(provider.reprocessingAppId, isNull);
      gate.complete(ReprocessSuccess(summaryConversation(overview: 'Done')));
      expect(await first, isTrue);
    });
  });

  group('template lists', () {
    test('a failed installed-template read is failed, never an empty list', () async {
      final fetches = SummaryTemplateFetches();
      final provider = summaryProvider(summaryConversation(), fetches: fetches);
      addTearDown(provider.dispose);
      final pending = provider.fetchAndCacheEnabledConversationApps();
      fetches.enabled.single.completeError(StateError('offline'));
      await pending;
      expect(provider.enabledTemplatesLoad, SummaryTemplatesLoad.failed);

      final retry = provider.fetchAndCacheEnabledConversationApps();
      fetches.enabled.last.complete([]);
      await retry;
      expect(provider.enabledTemplatesLoad, SummaryTemplatesLoad.loaded);
      expect(provider.cachedEnabledConversationApps, isEmpty);
    });

    test('an older installed-template read finishing late never overwrites a newer one', () async {
      final fetches = SummaryTemplateFetches();
      final provider = summaryProvider(summaryConversation(), fetches: fetches);
      addTearDown(provider.dispose);
      final older = provider.fetchAndCacheEnabledConversationApps();
      final newer = provider.fetchAndCacheEnabledConversationApps();
      fetches.enabled[1].complete([summaryApp('pg', 'Paul Graham')]);
      await newer;
      expect(provider.enabledTemplatesLoad, SummaryTemplatesLoad.loaded);

      fetches.enabled[0].completeError(StateError('stale timeout'));
      await older;
      expect(provider.enabledTemplatesLoad, SummaryTemplatesLoad.loaded, reason: 'a stale failure is dropped');
      expect(provider.cachedEnabledConversationApps.map((app) => app.id), ['pg']);

      final olderSuccess = provider.fetchAndCacheEnabledConversationApps();
      final newest = provider.fetchAndCacheEnabledConversationApps();
      fetches.enabled[3].complete([summaryApp('mm', 'Meeting Minutes')]);
      await newest;
      fetches.enabled[2].complete([]);
      await olderSuccess;
      expect(provider.cachedEnabledConversationApps.map((app) => app.id), ['mm'], reason: 'a stale list is dropped');
    });

    test('suggestions belong to one conversation', () async {
      final fetches = SummaryTemplateFetches();
      final provider = summaryProvider(summaryConversation(id: 'a'), fetches: fetches);
      addTearDown(provider.dispose);
      final pending = provider.fetchAndCacheSuggestedApps();
      fetches.suggested.single.complete([summaryApp('pg', 'Paul Graham')]);
      await pending;
      expect(provider.cachedSuggestedApps.map((app) => app.id), ['pg']);

      provider.setCachedConversation(summaryConversation(id: 'b'));
      expect(provider.cachedSuggestedApps, isEmpty);
      expect(provider.suggestedTemplatesLoad, SummaryTemplatesLoad.idle);
    });

    test('a suggestion response for a conversation the page left is dropped', () async {
      final fetches = SummaryTemplateFetches();
      final provider = summaryProvider(summaryConversation(id: 'a'), fetches: fetches);
      addTearDown(provider.dispose);
      final pending = provider.fetchAndCacheSuggestedApps();
      provider.setCachedConversation(summaryConversation(id: 'b'));
      fetches.suggested.single.complete([summaryApp('pg', 'Paul Graham')]);
      await pending;
      expect(provider.cachedSuggestedApps, isEmpty);
    });
  });

  test('reprocessQuery: a template sends app_id, Omi sends source=omi, legacy regenerate sends nothing', () {
    expect(reprocessQuery(appId: 'pg'), '?app_id=pg');
    expect(reprocessQuery(appId: 'pg', forceOmi: true), '?app_id=pg');
    expect(reprocessQuery(forceOmi: true), '?source=omi');
    expect(reprocessQuery(), '');
  });

  test('"Make this my default" writes the server preference: a template sets it, Omi clears it', () async {
    final writes = <String?>[];
    final provider = summaryProvider(
      summaryConversation(),
      writePreferredSummaryApp: (appId) async {
        writes.add(appId);
        return true;
      },
    );
    addTearDown(provider.dispose);
    expect(await provider.setDefaultSummaryTemplateAppId('pg'), isTrue);
    expect(await provider.setDefaultSummaryTemplateAppId(null), isTrue);
    expect(writes, ['pg', null]);
  });

  test('legacy Set Default persists the built-in through the shared writer', () async {
    final writes = <String?>[];
    final provider = summaryProvider(summaryConversation(), writePreferredSummaryApp: (id) async {
      writes.add(id);
      return true;
    });
    addTearDown(provider.dispose);
    expect(await provider.setPreferredSummarizationApp(builtInSummaryTemplateAppId), isTrue);
    expect(writes, [builtInSummaryTemplateAppId]);
    expect(provider.preferredSummarizationAppId, builtInSummaryTemplateAppId);
    expect(provider.defaultSummaryTemplateAppId, builtInSummaryTemplateAppId);
    expect(await provider.setDefaultSummaryTemplateAppId(null), isTrue);
    expect(writes, [builtInSummaryTemplateAppId, null]);
    expect(provider.defaultSummaryTemplateAppId, isNull);
  });

  test('a failed server preference write keeps the local default and reports false', () async {
    final provider = summaryProvider(
      summaryConversation(),
      writePreferredSummaryApp: (_) async => throw StateError('offline'),
    );
    addTearDown(provider.dispose);
    expect(await provider.setDefaultSummaryTemplateAppId('pg'), isFalse);
    expect(provider.defaultSummaryTemplateAppId, 'pg');
  });

  test('the default summary template is saved locally; null is Omi', () {
    final provider = summaryProvider(summaryConversation());
    addTearDown(provider.dispose);
    expect(provider.defaultSummaryTemplateAppId, 'omi-default-summary');
    provider.setDefaultSummaryTemplateAppId('pg');
    expect(provider.defaultSummaryTemplateAppId, 'pg');
    final otherUser = summaryProvider(summaryConversation());
    addTearDown(otherUser.dispose);
    SharedPreferencesUtil().uid = 'someone-else';
    expect(otherUser.defaultSummaryTemplateAppId, 'omi-default-summary', reason: 'the default is per signed-in user');
    SharedPreferencesUtil().uid = '';
    expect(provider.defaultSummaryTemplateAppId, 'pg');
    provider.setDefaultSummaryTemplateAppId(null);
    expect(provider.defaultSummaryTemplateAppId, isNull);
  });
}
