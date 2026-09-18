import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';
import 'package:omi/providers/conversation_provider.dart';

/// A conversation whose first-party summary lives entirely in `sections`, with
/// whatever app results the case under test needs.
ServerConversation _conversation({List<AppResponse> appResults = const []}) {
  final structured = Structured('Sprint sync', 'Short compatibility paragraph.', emoji: '🧠');
  structured.sections = [
    const wire.GeneratedSection(
      heading: 'Decisions',
      bodyMarkdown: 'Ship the beta on Friday',
      sourceSegmentIds: ['segment-1'],
    ),
  ];
  return ServerConversation(
    id: 'conv-1',
    createdAt: DateTime(2026, 7, 1, 9).toUtc(),
    structured: structured,
    appResults: appResults,
  );
}

ConversationDetailProvider _providerFor(ServerConversation conversation) {
  final provider = ConversationDetailProvider();
  addTearDown(provider.dispose);
  provider.selectedDate = conversationLocalDayKey(conversation.createdAt);
  provider.setCachedConversation(conversation);
  return provider;
}

class _PersistingProvider extends ConversationDetailProvider {
  _PersistingProvider(this.handler);

  final Future<bool> Function(String conversationId, String? appId, String content) handler;

  @override
  Future<bool> persistSummaryEdit(String conversationId, String? appId, String content) {
    return handler(conversationId, appId, content);
  }
}

ConversationDetailProvider _providerWithPersistence(
  ServerConversation conversation,
  Future<bool> Function(String conversationId, String? appId, String content) handler,
) {
  final provider = _PersistingProvider(handler);
  addTearDown(provider.dispose);
  provider.selectedDate = conversationLocalDayKey(conversation.createdAt);
  provider.setCachedConversation(conversation);
  return provider;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('an app result with empty content is not treated as the summary', () {
    // Regression: the old selector returned appResults[0] unconditionally.
    // A result with empty content then carried a non-null appId, which
    // suppressed the structured sections (AppResultDetailWidget only renders
    // them when appId == null) while the empty content sent the widget into its
    // "no summary available for this app" placeholder — a conversation with a
    // full sections summary rendered as having no summary at all.
    final conversation = _conversation(appResults: [AppResponse('   ', appId: 'app-1')]);

    final summary = _providerFor(conversation).getSummarySelection();

    expect(summary.kind, ConversationSummaryKind.overview);
    expect(summary.appId, isNull);
    expect(summary.content, 'Short compatibility paragraph.');
  });

  test('the first app result that carries content is the summary', () {
    final conversation = _conversation(appResults: [
      AppResponse('', appId: 'empty-app'),
      AppResponse('App summary', appId: 'app-2'),
    ]);

    final summary = _providerFor(conversation).getSummarySelection();

    expect(summary.appId, 'app-2');
    expect(summary.content, 'App summary');
  });

  test('sections alone still produce a first-party summary when no app ran', () {
    final conversation = _conversation();

    final summary = _providerFor(conversation).getSummarySelection();

    expect(summary.kind, ConversationSummaryKind.overview);
    expect(summary.appId, isNull);
    expect(summary.content, 'Short compatibility paragraph.');
  });

  test('duplicate app ids are read-only instead of editing the first match', () async {
    final conversation = _conversation(appResults: [
      AppResponse('First app summary', appId: 'duplicate'),
      AppResponse('Second app summary', appId: 'duplicate'),
    ]);
    final provider = _providerFor(conversation);
    final selection = provider.getSummarySelection();

    expect(selection.canEdit(conversation), isFalse);
    await provider.saveEditingSummarySelection(selection, 'Edited summary');

    expect(conversation.appResults[0].content, 'First app summary');
    expect(conversation.appResults[1].content, 'Second app summary');
  });

  test('a stale app selection cannot edit after its result changes', () async {
    final conversation = _conversation(appResults: [AppResponse('Original app summary', appId: 'app-1')]);
    final provider = _providerFor(conversation);
    final selection = provider.getSummarySelection();
    conversation.appResults[0].content = 'Refreshed app summary';

    expect(selection.canEdit(conversation), isFalse);
    await provider.saveEditingSummarySelection(selection, 'Edited summary');

    expect(conversation.appResults[0].content, 'Refreshed app summary');
  });

  test('a successful first-party edit clears sections and preserves unrelated state', () async {
    final conversation = _conversation();
    final action = ActionItem('Follow up', completed: false);
    final event = Event('Review', DateTime.utc(2026, 7, 2), 30);
    conversation.structured.actionItems = [action];
    conversation.structured.events = [event];
    var persistCalls = 0;
    String? persistedConversationId;
    String? persistedAppId;
    String? persistedContent;
    final provider = _providerWithPersistence(conversation, (conversationId, appId, content) async {
      persistCalls++;
      persistedConversationId = conversationId;
      persistedAppId = appId;
      persistedContent = content;
      return true;
    });
    final selection = provider.getSummarySelection();

    await provider.saveEditingSummarySelection(selection, 'Edited overview');

    expect(conversation.structured.overview, 'Edited overview');
    expect(conversation.structured.sections, isEmpty);
    expect(conversation.structured.actionItems.single, same(action));
    expect(conversation.structured.events.single, same(event));
    expect(persistCalls, 1);
    expect(persistedConversationId, 'conv-1');
    expect(persistedAppId, isNull);
    expect(persistedContent, 'Edited overview');
  });

  test('a failed first-party edit restores the previous overview and sections', () async {
    final conversation = _conversation();
    final oldOverview = conversation.structured.overview;
    final oldSections = List<Section>.from(conversation.structured.sections);
    final provider = _providerWithPersistence(conversation, (conversationId, appId, content) async => false);
    final selection = provider.getSummarySelection();

    await provider.saveEditingSummarySelection(selection, 'Edited overview');

    expect(conversation.structured.overview, oldOverview);
    expect(conversation.structured.sections, orderedEquals(oldSections));
  });

  test('app edits preserve first-party sections and unrelated state', () async {
    final conversation = _conversation(appResults: [AppResponse('App original', appId: 'app-1')]);
    final action = ActionItem('Follow up', completed: false);
    final event = Event('Review', DateTime.utc(2026, 7, 2), 30);
    conversation.structured.actionItems = [action];
    conversation.structured.events = [event];
    final oldSections = List<Section>.from(conversation.structured.sections);
    var persistCalls = 0;
    String? persistedConversationId;
    String? persistedAppId;
    String? persistedContent;
    final provider = _providerWithPersistence(conversation, (conversationId, appId, content) async {
      persistCalls++;
      persistedConversationId = conversationId;
      persistedAppId = appId;
      persistedContent = content;
      return true;
    });
    final selection = provider.getSummarySelection();

    await provider.saveEditingSummarySelection(selection, 'Edited app summary');

    expect(conversation.appResults.single.content, 'Edited app summary');
    expect(conversation.structured.sections, orderedEquals(oldSections));
    expect(conversation.structured.actionItems.single, same(action));
    expect(conversation.structured.events.single, same(event));
    expect(persistCalls, 1);
    expect(persistedConversationId, 'conv-1');
    expect(persistedAppId, 'app-1');
    expect(persistedContent, 'Edited app summary');
  });

  test('a failed edit does not roll back over a refreshed conversation', () async {
    final conversation = _conversation();
    final completion = Completer<bool>();
    final provider = _providerWithPersistence(conversation, (conversationId, appId, content) => completion.future);
    final selection = provider.getSummarySelection();
    final saveFuture = provider.saveEditingSummarySelection(selection, 'Edited overview');

    final refreshed = _conversation();
    refreshed.structured.overview = 'Refreshed overview';
    provider.setCachedConversation(refreshed);
    completion.complete(false);
    await saveFuture;

    expect(refreshed.structured.overview, 'Refreshed overview');
    expect(refreshed.structured.sections, isNotEmpty);
  });

  test('a failed edit does not roll back over a newer edit on the same conversation', () async {
    final conversation = _conversation();
    final completion = Completer<bool>();
    final provider = _providerWithPersistence(conversation, (conversationId, appId, content) => completion.future);
    final selection = provider.getSummarySelection();
    final saveFuture = provider.saveEditingSummarySelection(selection, 'First edit');

    conversation.structured.overview = 'Newer edit';
    completion.complete(false);
    await saveFuture;

    expect(conversation.structured.overview, 'Newer edit');
  });
}
