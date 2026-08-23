import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/models/chat_evidence_reference.dart';
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
        final reference = ChatEvidenceReference(
          id: 'request-${state.wireValue}',
          kind: ChatEvidenceReferenceKind.request,
          state: state,
          requestId: 'request-${state.wireValue}',
        );

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: Column(
                children: [
                  const Text('The answer remains available.'),
                  ChatEvidenceReferenceCard(reference: reference),
                ],
              ),
            ),
          ),
        );

        expect(find.text('The answer remains available.'), findsOneWidget);
        expect(find.text(reference.statusLabel), findsOneWidget);
        expect(reference.canOpen, isFalse);
        expect(find.byType(InkWell), findsNothing);
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
