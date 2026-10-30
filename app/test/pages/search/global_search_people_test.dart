import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/search.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/search/global_search.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/people_provider.dart';

class _Source extends GlobalSearchSource {
  const _Source();

  @override
  Future<ApiResult<SearchOverview>> overview() async =>
      const ApiFailure(ApiProblem(ApiProblemKind.notFound, statusCode: 404));

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

Person _person(String id, String name, {String confidence = 'unverified'}) => Person(
      id: id,
      name: name,
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
      confidence: confidence,
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('the People scope hosts the shared list: the search field filters it, no management chrome',
      (tester) async {
    final people = PeopleProvider(
      loadPeople: () async => PeopleListResponse(people: [
        _person('p-maya', 'Maya Chen', confidence: 'confirmed'),
        _person('p-because', 'Because'),
        _person('p-cs', 'Cs'),
        _person('p-thanks', 'Thanks'),
      ]),
    );
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<PeopleProvider>.value(value: people),
        ChangeNotifierProvider(create: (_) => FolderProvider(foldersFetcher: () async => <Folder>[])),
      ],
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: GlobalSearchPage(source: _Source())),
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('search_tile_people')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('search_people_list')), findsOneWidget);
    expect(find.text('Maya Chen'), findsOneWidget);
    expect(find.text('Search people'), findsOneWidget);
    // Settings-only chrome stays in Settings, even with three unsure people.
    expect(find.byKey(const Key('people_clean_up_banner')), findsNothing);
    expect(find.byKey(const Key('people_select')), findsNothing);

    // Settings can still have a selection while the search overlay is mounted.
    people.beginSelection('p-cs');
    await tester.pumpAndSettle();
    expect(find.byType(Dismissible), findsWidgets);

    await tester.enterText(
        find.descendant(of: find.byKey(const ValueKey('global_search_field')), matching: find.byType(TextField)), 'cs');
    await tester.pumpAndSettle();
    expect(find.text('Cs'), findsOneWidget);
    expect(find.text('Maya Chen'), findsNothing);

    // The row menu still works here, without Select.
    await tester.longPress(find.text('Cs'));
    await tester.pumpAndSettle();
    expect(find.text('Pin'), findsOneWidget);
    expect(find.text('Select'), findsNothing);
    expect(find.text('Open'), findsOneWidget);
  });
}
