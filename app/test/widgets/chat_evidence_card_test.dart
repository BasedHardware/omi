import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/message.dart';
import 'package:omi/models/chat_evidence_reference.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/widgets/components/chat_evidence_card.dart';

void main() {
  testWidgets(
    'renders a supplemental evidence card without replacing the answer text',
    (tester) async {
      var opened = false;
      const reference = ChatEvidenceReference(
        id: 'keyframe-1',
        kind: ChatEvidenceReferenceKind.keyframe,
        state: ChatEvidenceReferenceState.available,
        frameId: 'keyframe-1',
        title: 'Screen keyframe',
        summary: 'Editor window',
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Column(
              children: [
                const Text('The answer remains visible.'),
                ChatEvidenceReferenceCard(
                  reference: reference,
                  onOpen: () => opened = true,
                ),
              ],
            ),
          ),
        ),
      );

      expect(find.text('The answer remains visible.'), findsOneWidget);
      expect(find.text('Screen keyframe'), findsOneWidget);
      expect(find.text('Editor window'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('chat-evidence-keyframe-1')));
      expect(opened, isTrue);
    },
  );

  testWidgets(
    'renders honest non-blocking states and exposes an accessible label',
    (tester) async {
      const states = [
        ChatEvidenceReferenceState.loading,
        ChatEvidenceReferenceState.offline,
        ChatEvidenceReferenceState.pruned,
        ChatEvidenceReferenceState.failed,
      ];

      for (final state in states) {
        final reference = ChatEvidenceReference(
          id: 'reference-${state.wireValue}',
          kind: ChatEvidenceReferenceKind.screen,
          state: state,
        );
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: Column(
                children: [
                  const Text('Text answer'),
                  ChatEvidenceReferenceCard(reference: reference),
                ],
              ),
            ),
          ),
        );

        expect(find.text('Text answer'), findsOneWidget);
        expect(find.text(reference.statusLabel), findsOneWidget);
        final semantics = tester.getSemantics(
          find.byKey(ValueKey('chat-evidence-${reference.id}')),
        );
        expect(semantics.label, contains(reference.accessibilityLabel));
      }
    },
  );

  testWidgets(
    'keeps the answer visible for loading and offline frame requests without actions',
    (tester) async {
      for (final state in [
        ChatEvidenceReferenceState.loading,
        ChatEvidenceReferenceState.offline,
      ]) {
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
            home: Scaffold(
              body: buildMessageWidget(
                message,
                (_) {},
                false,
                false,
                null,
                (_) {},
                setMessageNps,
              ),
            ),
          ),
        );

        expect(find.text('The answer remains available.'), findsOneWidget);
        expect(find.text(reference.statusLabel), findsOneWidget);
        expect(
          find.ancestor(
            of: find.byKey(ValueKey('chat-evidence-${reference.id}')),
            matching: find.byType(InkWell),
          ),
          findsNothing,
        );

        var opened = false;
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: ChatEvidenceReferenceCard(
                reference: reference,
                onOpen: () => opened = true,
              ),
            ),
          ),
        );

        expect(find.text(reference.statusLabel), findsOneWidget);
        expect(reference.canOpen, isFalse);
        expect(find.byType(InkWell), findsNothing);
        await tester.tap(find.byKey(ValueKey('chat-evidence-${reference.id}')));
        expect(opened, isFalse);
        final semantics = tester.getSemantics(
          find.byKey(ValueKey('chat-evidence-${reference.id}')),
        );
        expect(semantics.label, contains(reference.accessibilityLabel));
      }
    },
  );

  testWidgets('empty envelopes render no supplemental chrome', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: ChatEvidenceReferenceList(
            envelope: ChatEvidenceReferenceEnvelope(references: []),
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('chat-evidence-reference-list')),
      findsNothing,
    );
  });
}
