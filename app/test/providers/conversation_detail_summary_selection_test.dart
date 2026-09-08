import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/providers/conversation_provider.dart';

/// A conversation whose first-party summary lives entirely in `sections`, with
/// whatever app results the case under test needs.
ServerConversation _conversation({List<AppResponse> appResults = const []}) {
  final structured = Structured('Sprint sync', 'Short compatibility paragraph.', emoji: '🧠');
  structured.sections = [
    const wire.GeneratedSection(heading: 'Decisions', bodyMarkdown: 'Ship the beta on Friday'),
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

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('an app result with empty content is not treated as the summary', () {
    // Regression: getSummarizedApp() returned appResults[0] unconditionally.
    // A result with empty content then carried a non-null appId, which
    // suppressed the structured sections (AppResultDetailWidget only renders
    // them when appId == null) while the empty content sent the widget into its
    // "no summary available for this app" placeholder — a conversation with a
    // full sections summary rendered as having no summary at all.
    final conversation = _conversation(appResults: [AppResponse('   ', appId: 'app-1')]);

    final summary = _providerFor(conversation).getSummarizedApp();

    expect(summary, isNotNull);
    expect(summary!.appId, isNull, reason: 'a null appId is what lets the structured sections render');
    expect(summary.content, 'Short compatibility paragraph.');
  });

  test('the first app result that carries content is the summary', () {
    final conversation = _conversation(appResults: [
      AppResponse('', appId: 'empty-app'),
      AppResponse('App summary', appId: 'app-2'),
    ]);

    final summary = _providerFor(conversation).getSummarizedApp();

    expect(summary!.appId, 'app-2');
    expect(summary.content, 'App summary');
  });

  test('sections alone still produce a first-party summary when no app ran', () {
    final conversation = _conversation();

    final summary = _providerFor(conversation).getSummarizedApp();

    expect(summary!.appId, isNull);
    expect(summary.content, 'Short compatibility paragraph.');
  });
}
