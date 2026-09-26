import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/chat/widgets/typing_indicator.dart';
import 'package:omi/ui/ui.dart';

void main() {
  group('TypingIndicator', () {
    testWidgets('is the Omi mark chasing while Omi thinks', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: Scaffold(body: Center(child: TypingIndicator()))));

      final logo = tester.widget<OmiRingLogo>(find.byType(OmiRingLogo));
      expect(logo.mode, OmiRingMode.chase);
      expect(tester.hasRunningAnimations, isTrue);
    });

    testWidgets('stands still under Reduce Motion', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: MediaQuery(
            data: MediaQueryData(disableAnimations: true),
            child: Scaffold(body: Center(child: TypingIndicator())),
          ),
        ),
      );
      await tester.pump();
      expect(tester.hasRunningAnimations, isFalse);
    });

    testWidgets('disposes cleanly when the reply arrives', (tester) async {
      await tester.pumpWidget(const MaterialApp(home: Scaffold(body: Center(child: TypingIndicator()))));
      await tester.pumpWidget(const MaterialApp(home: Scaffold(body: SizedBox.shrink())));
      expect(find.byType(TypingIndicator), findsNothing);
    });
  });
}
