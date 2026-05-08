import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/chat/widgets/genui_widgets.dart';

void main() {
  group('ActionButtonsWidget', () {
    testWidgets('renders title and sends tapped label back to chat', (tester) async {
      String? sentMessage;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActionButtonsWidget(
              props: const {
                'title': 'Quick actions',
                'buttons': ['Share location', 'Find nearby coffee'],
              },
              sendMessage: (message) => sentMessage = message,
            ),
          ),
        ),
      );

      expect(find.text('Quick actions'), findsOneWidget);
      expect(find.text('Share location'), findsOneWidget);
      expect(find.text('Find nearby coffee'), findsOneWidget);

      await tester.tap(find.text('Find nearby coffee'));
      await tester.pump();

      expect(sentMessage, 'Find nearby coffee');
    });

    testWidgets('renders nothing when no buttons are provided', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: ActionButtonsWidget(
              props: {'buttons': []},
              sendMessage: _noop,
            ),
          ),
        ),
      );

      expect(find.byType(SizedBox), findsOneWidget);
      expect(find.text('Quick actions'), findsNothing);
    });
  });
}

void _noop(String _) {}
