import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/search/global_search.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/people_provider.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

/// Answers search from memory; nothing reaches a backend.
class _Source extends GlobalSearchSource {
  const _Source();

  @override
  Future<ApiResult<SearchOverview>> overview() async => const ApiSuccess(SearchOverview(starred: 1, people: 2));

  @override
  Future<ConversationSearchResult> conversations(String query,
          {String? speakerId, DateTime? startDate, DateTime? endDate}) async =>
      const ConversationSearchResult(
          items: [], currentPage: 1, totalPages: 1, outcome: ConversationSearchResultOutcome.success);

  @override
  Future<List<ServerConversation>> conversationsIn({String? folderId, bool starred = false}) async => const [];

  @override
  Future<ApiResult<List<DailySummary>>> recaps(String query) async => const ApiSuccess([]);

  @override
  Future<ApiResult<List<ActionItemWithMetadata>>> tasks(String query) async => const ApiSuccess([]);

  @override
  Future<ApiResult<List<MemorySearchHit>>> memories(String query) async => const ApiSuccess([]);
}

ServerConversation _conversation(String id, String title, int hour) => ServerConversation(
    id: id,
    createdAt: DateTime(2026, 10, 4, hour),
    startedAt: DateTime(2026, 10, 4, hour),
    structured: Structured(title, 'Overview'));

/// Run on Simulator with OMI_APP_PROFILE=local_dev and OMI_IOS_SWIFTUI=true.
void main() => runNativeHostSuite((checkNativeHost) {
      testWidgets('the native library selects rows natively and shows the bottom bar', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        final conversations = ConversationProvider(isSignedIn: () => true)
          ..conversations = [_conversation('a', 'Standup', 9), _conversation('b', 'Retro', 11)]
          ..groupConversationsByDate();
        addTearDown(conversations.dispose);
        await tester.pumpWidget(nativeHostApp(
            const Scaffold(body: ConversationsPage(requestInitialLoad: false, nativeLibrary: true)),
            providers: [ChangeNotifierProvider<ConversationProvider>.value(value: conversations)]));
        await checkNativeHost(tester, 'native-conversation-library-search-library-dark');

        await nativeProjectedRow(tester, 'library_select').action!(null);
        await tester.pump(const Duration(seconds: 1));
        expect(conversations.isSelectionModeActive, isTrue);
        final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
        await surface.selection!.action(['library_conversation_a', 'library_conversation_b']);
        await tester.pump(const Duration(seconds: 1));
        expect(conversations.selectedConversationIds, {'a', 'b'});
        expect(nativeProjectedRow(tester, 'library_merge').enabled, isTrue);
        await checkNativeHost(tester, 'native-conversation-library-search-selection-dark');

        await nativeProjectedRow(tester, 'library_cancel').action!(null);
        await tester.pump(const Duration(seconds: 1));
        expect(conversations.isSelectionModeActive, isFalse);
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pump();
        expect(tester.takeException(), isNull);
      });

      testWidgets('the native search date filter opens as a system sheet', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        await tester.pumpWidget(nativeHostApp(const Scaffold(body: GlobalSearchPage(source: _Source()))));
        await checkNativeHost(tester, 'native-conversation-library-search-search-dark');

        var finished = false;
        unawaited(Future.sync(() => nativeProjectedRow(tester, 'search_date').action!(null))
            .whenComplete(() => finished = true));
        await tester.pump(const Duration(seconds: 2));
        expect(finished, isFalse, reason: 'The native sheet waits for a choice');
        expect(find.byKey(const Key('date_range_done')), findsNothing, reason: 'No Flutter calendar opened');
        expect(await captureNativeHostScreenshot('native-conversation-library-search-date-dark'), isNotEmpty);

        // Leaving the page withdraws the sheet.
        await tester.pumpWidget(const SizedBox.shrink());
        for (var i = 0; i < 10 && !finished; i++) {
          await tester.pump(const Duration(milliseconds: 500));
        }
        expect(finished, isTrue);
        expect(tester.takeException(), isNull);
      });

      testWidgets('the People scope of search renders natively', (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        final people = PeopleProvider(
            loadPeople: () async => PeopleListResponse(people: [
                  Person(id: 'ada', name: 'Ada', createdAt: DateTime(2026), updatedAt: DateTime(2026), pinned: true),
                  Person(id: 'sam', name: 'Sam', createdAt: DateTime(2026), updatedAt: DateTime(2026)),
                ]));
        addTearDown(people.dispose);
        await tester.pumpWidget(nativeHostApp(const Scaffold(body: GlobalSearchPage(source: _Source())),
            providers: [ChangeNotifierProvider<PeopleProvider>.value(value: people)]));
        await tester.pump(const Duration(seconds: 1));
        await nativeProjectedRow(tester, 'search_people').action!(null);
        await tester.pump(const Duration(seconds: 1));
        await checkNativeHost(tester, 'native-conversation-library-search-people-dark');
        expect(nativeProjectedRow(tester, 'person_sam').options.keys, ['open', 'pin', 'why', 'delete']);
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pump();
        expect(tester.takeException(), isNull);
      });
    });
