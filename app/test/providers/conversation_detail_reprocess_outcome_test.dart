import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

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

    test('409 conversation_processing_in_progress is busy', () {
      final result = reprocessResultFromResponse(_json(409, {
        'detail': {'code': 'conversation_processing_in_progress', 'message': 'Already processing'},
      }));
      expect(result, isA<ReprocessBusy>());
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

    test('502 app_result_failed and 500 are failures', () {
      expect(
        reprocessResultFromResponse(_json(502, {
          'detail': {'code': 'app_result_failed', 'message': 'no content'},
        })),
        isA<ReprocessFailed>(),
      );
      expect(reprocessResultFromResponse(http.Response('', 500)), isA<ReprocessFailed>());
    });
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
    expect(provider.defaultSummaryTemplateAppId, isNull);
    provider.setDefaultSummaryTemplateAppId('pg');
    expect(provider.defaultSummaryTemplateAppId, 'pg');
    final otherUser = summaryProvider(summaryConversation());
    addTearDown(otherUser.dispose);
    SharedPreferencesUtil().uid = 'someone-else';
    expect(otherUser.defaultSummaryTemplateAppId, isNull, reason: 'the default is per signed-in user');
    SharedPreferencesUtil().uid = '';
    expect(provider.defaultSummaryTemplateAppId, 'pg');
    provider.setDefaultSummaryTemplateAppId(null);
    expect(provider.defaultSummaryTemplateAppId, isNull);
  });
}
