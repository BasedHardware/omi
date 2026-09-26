import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/folder_tabs.dart';
import 'package:omi/providers/conversation_provider.dart';

/// Rev 3 Conversations source chips (All · Starred · Pendant · Glasses · Phone · Imported): the
/// list endpoint's existing `sources` filter, never a client-side filter that would hide older
/// matches.
void main() {
  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  ServerConversation conversation(ConversationSource? source) => ServerConversation(
        id: 'c-${source?.name}',
        createdAt: DateTime.utc(2026, 9, 25),
        structured: Structured('Title', 'Overview', emoji: '', category: 'other'),
        source: source,
      );

  group('conversationCollectionUrl sources', () {
    test('no source leaves the query as it was', () {
      final uri = Uri.parse(conversationCollectionUrl('https://api.test/'));
      expect(uri.queryParameters.containsKey('sources'), isFalse);
      expect(uri.queryParameters['statuses'], '');
    });

    test('several sources list completed conversations: the server allows one `in` filter per query', () {
      final uri = Uri.parse(conversationCollectionUrl('https://api.test/', sources: ['omi', 'friend']));
      expect(uri.queryParameters['sources'], 'omi,friend');
      expect(uri.queryParameters['statuses'], 'completed');
    });

    test('one source, or one explicit status, keeps the statuses', () {
      final single = Uri.parse(conversationCollectionUrl('https://api.test/', sources: ['phone']));
      expect(single.queryParameters['sources'], 'phone');
      expect(single.queryParameters['statuses'], '');
      final explicit = Uri.parse(conversationCollectionUrl(
        'https://api.test/',
        sources: ['omi', 'friend'],
        statuses: [ConversationStatus.processing],
      ));
      expect(explicit.queryParameters['statuses'], 'processing');
    });
  });

  group('ConversationSourceFilter', () {
    test('every chip names server sources the list endpoint accepts', () {
      expect(ConversationSourceFilter.all.apiSources, isEmpty);
      for (final filter in ConversationSourceFilter.values.where((f) => f != ConversationSourceFilter.all)) {
        expect(filter.apiSources, isNotEmpty, reason: filter.name);
        expect(filter.apiSources.length, lessThanOrEqualTo(20), reason: 'MAX_IN_FILTER_VALUES');
      }
      expect(ConversationSourceFilter.pendant.apiSources, containsAll(['omi', 'friend']));
      expect(ConversationSourceFilter.glasses.apiSources, containsAll(['openglass', 'rayban_meta', 'frame']));
      expect(ConversationSourceFilter.phone.apiSources, contains('phone'));
      expect(ConversationSourceFilter.imported.apiSources, containsAll(['plaud', 'bee', 'limitless', 'fieldy']));
    });

    test('matches by source; a source this app cannot name stays (the server chose it)', () {
      final phone = conversation(ConversationSource.phone);
      expect(ConversationSourceFilter.all.matches(phone), isTrue);
      expect(ConversationSourceFilter.phone.matches(phone), isTrue);
      expect(ConversationSourceFilter.glasses.matches(phone), isFalse);
      expect(ConversationSourceFilter.pendant.matches(conversation(ConversationSource.omi)), isTrue);
      expect(ConversationSourceFilter.imported.matches(conversation(null)), isTrue);
    });
  });

  group('ConversationProvider source filter', () {
    late List<Uri> requests;

    ConversationProvider makeProvider() {
      requests = [];
      final api = ConversationApi(
        baseUrl: 'https://api.test/',
        send: (request) async {
          requests.add(Uri.parse(request.url));
          return http.Response('[]', 200);
        },
      );
      final provider = ConversationProvider(conversationApi: api, isSignedIn: () => true);
      addTearDown(provider.dispose);
      return provider;
    }

    Uri lastList() => requests.lastWhere((uri) => uri.path == '/v1/conversations');

    test('a source asks the server for it and clears the folder and Starred', () async {
      final provider = makeProvider();
      provider.selectedFolderId = 'folder-1';
      provider.showStarredOnly = true;

      provider.setSourceFilter(ConversationSourceFilter.glasses);
      await pumpEventQueue();

      expect(provider.sourceFilter, ConversationSourceFilter.glasses);
      expect(provider.selectedFolderId, isNull);
      expect(provider.showStarredOnly, isFalse);
      final query = lastList().queryParameters;
      expect(query['sources'], 'openglass,rayban_meta,frame');
      expect(query['statuses'], 'completed');
      expect(query.containsKey('folder_id'), isFalse);
      expect(query.containsKey('starred'), isFalse);
    });

    test('Starred or a folder clears the source', () async {
      final provider = makeProvider();
      provider.setSourceFilter(ConversationSourceFilter.phone);
      await pumpEventQueue();

      provider.toggleStarredFilter();
      await pumpEventQueue();
      expect(provider.sourceFilter, ConversationSourceFilter.all);
      expect(lastList().queryParameters.containsKey('sources'), isFalse);
      expect(lastList().queryParameters['starred'], 'true');

      provider.toggleStarredFilter();
      provider.setSourceFilter(ConversationSourceFilter.pendant);
      await pumpEventQueue();
      await provider.filterByFolder('folder-2');
      expect(provider.sourceFilter, ConversationSourceFilter.all);
      expect(lastList().queryParameters['folder_id'], 'folder-2');
      expect(lastList().queryParameters.containsKey('sources'), isFalse);
    });

    test('choosing the current source again does not refetch', () async {
      final provider = makeProvider();
      provider.setSourceFilter(ConversationSourceFilter.imported);
      await pumpEventQueue();
      final count = requests.length;
      provider.setSourceFilter(ConversationSourceFilter.imported);
      await pumpEventQueue();
      expect(requests.length, count);
    });
  });

  group('FolderTabs source chips', () {
    Future<void> pumpTabs(
      WidgetTester tester, {
      required ConversationSourceFilter source,
      ValueChanged<ConversationSourceFilter>? onSourceSelected,
      VoidCallback? onStarredToggle,
    }) {
      return tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Column(
              children: [
                FolderTabs(
                  folders: const [],
                  selectedFolderId: null,
                  onFolderSelected: (_) {},
                  showStarredOnly: false,
                  onStarredToggle: onStarredToggle ?? () {},
                  sourceFilter: source,
                  onSourceSelected: onSourceSelected,
                ),
              ],
            ),
          ),
        ),
      );
    }

    testWidgets('Pendant · Glasses · Phone · Imported follow All and Starred', (tester) async {
      tester.view.physicalSize = const Size(1400, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await pumpTabs(tester, source: ConversationSourceFilter.all, onSourceSelected: (_) {});

      final labels = ['All', 'Starred', 'Pendant', 'Glasses', 'Phone', 'Imported'];
      final xs = [for (final label in labels) tester.getTopLeft(find.text(label)).dx];
      expect(xs, orderedEquals([...xs]..sort()));
    });

    testWidgets('a chip picks its source; the selected chip or All goes back to everything', (tester) async {
      final picked = <ConversationSourceFilter>[];
      await pumpTabs(tester, source: ConversationSourceFilter.all, onSourceSelected: picked.add);
      await tester.tap(find.text('Glasses'));
      expect(picked, [ConversationSourceFilter.glasses]);

      await pumpTabs(tester, source: ConversationSourceFilter.glasses, onSourceSelected: picked.add);
      final semantics = tester.ensureSemantics();
      expect(tester.getSemantics(find.byKey(const ValueKey('conversation_source_glasses'))),
          matchesSemantics(isButton: true, isSelected: true, hasSelectedState: true, hasTapAction: true, label: 'Glasses'));
      expect(tester.getSemantics(find.byKey(const ValueKey('conversation_source_all'))),
          matchesSemantics(isButton: true, hasSelectedState: true, hasTapAction: true, label: 'All'));
      semantics.dispose();

      await tester.tap(find.text('Glasses'));
      expect(picked.last, ConversationSourceFilter.all);
      picked.clear();
      await tester.tap(find.text('All'));
      expect(picked, [ConversationSourceFilter.all]);
    });

    testWidgets('without a source handler the strip shows no source chips', (tester) async {
      await pumpTabs(tester, source: ConversationSourceFilter.all);
      expect(find.text('Pendant'), findsNothing);
      expect(find.text('Imported'), findsNothing);
    });
  });
}
