import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';

import '../helpers/summary_fixtures.dart';

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('displayed summary selection', () {
    test('a reader chip pick overrides the canonical selection for every copy/read surface', () {
      // Omi's notes and a template result both exist; canonically the template is first.
      final provider = summaryProvider(
        summaryConversation(
          overview: 'Omi overview of the drive.',
          appResults: [AppResponse('Essay about the drive.', appId: 'pg')],
        ),
        catalog: [summaryApp('pg', 'Paul Graham')],
      );
      addTearDown(provider.dispose);

      expect(provider.getSummarySelection().isApp, isTrue, reason: 'canonical selection is the template');
      expect(provider.getSummarySelection().content, 'Essay about the drive.');

      provider.showSummarySource(ConversationSummarySelection.firstParty(provider.conversation));
      final displayed = provider.getDisplayedSummarySelection();
      expect(displayed.isApp, isFalse);
      expect(displayed.content, 'Omi overview of the drive.');
    });

    test('without a reader pick the displayed selection is the canonical one', () {
      final provider = summaryProvider(
        summaryConversation(
          overview: 'Omi overview of the drive.',
          appResults: [AppResponse('Essay about the drive.', appId: 'pg')],
        ),
        catalog: [summaryApp('pg', 'Paul Graham')],
      );
      addTearDown(provider.dispose);

      expect(provider.getDisplayedSummarySelection().content, 'Essay about the drive.');
    });
  });
}
