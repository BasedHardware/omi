import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/chat_evidence_reference.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';

void main() {
  testWidgets('messages decode evidence but render only the answer for every evidence state', (tester) async {
    for (final state in ChatEvidenceReferenceState.values) {
      final message = ServerMessage.fromJson({
        'id': 'message-${state.wireValue}',
        'created_at': '2026-08-23T12:00:00Z',
        'text': 'The answer remains available.',
        'sender': 'ai',
        'type': 'text',
        'evidence': {
          'schema_version': 1,
          'request_id': 'request-${state.wireValue}',
          'references': [
            {
              'id': 'request-${state.wireValue}',
              'kind': 'request',
              'state': state.wireValue,
              'request_id': 'request-${state.wireValue}',
            },
          ],
        },
      });
      final reference = message.evidenceEnvelope!.references.single;

      void setMessageNps(int score, {String? reason}) {}

      await tester.pumpWidget(
        MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: buildMessageWidget(message, (_) {}, false, false, null, (_) {}, setMessageNps)),
        ),
      );

      expect(message.memories, isEmpty);
      expect(reference.state, state);
      expect(find.text('The answer remains available.'), findsOneWidget);
      expect(find.byWidgetPredicate((widget) => widget.key.toString().contains('chat-evidence-')), findsNothing);
      expect(find.text(reference.statusLabel), findsNothing);
    }
  });
}
