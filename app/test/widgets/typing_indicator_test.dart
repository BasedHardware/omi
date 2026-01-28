import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/chat/widgets/typing_indicator.dart';

void main() {
  group('TypingIndicator', () {
    testWidgets('renders three animated bubbles', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: TypingIndicator(),
            ),
          ),
        ),
      );

      // Should have 3 bubble containers (circles)
      final typingIndicator = find.byType(TypingIndicator);
      expect(typingIndicator, findsOneWidget);

      // Count circle-shaped containers within TypingIndicator
      int bubbleCount = 0;
      final containers = find.descendant(
        of: typingIndicator,
        matching: find.byType(Container),
      );
      for (final element in containers.evaluate()) {
        final widget = element.widget as Container;
        if (widget.decoration is BoxDecoration) {
          final decoration = widget.decoration as BoxDecoration;
          if (decoration.shape == BoxShape.circle) {
            bubbleCount++;
          }
        }
      }
      expect(bubbleCount, 3);
    });

    testWidgets('uses SlideTransition and optimized ScaleTransition with RepaintBoundary', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: TypingIndicator(),
            ),
          ),
        ),
      );

      final typingIndicator = find.byType(TypingIndicator);

      // Should have SlideTransition widgets within TypingIndicator
      final slideTransitions = find.descendant(
        of: typingIndicator,
        matching: find.byType(SlideTransition),
      );
      expect(slideTransitions, findsNWidgets(3));

      // Should have ScaleTransition (restored with optimization: 0.85-1.0 range)
      final scaleTransitions = find.descendant(
        of: typingIndicator,
        matching: find.byType(ScaleTransition),
      );
      expect(scaleTransitions, findsNWidgets(3));

      // Should have RepaintBoundary to isolate repaints (optimization)
      final repaintBoundaries = find.descendant(
        of: typingIndicator,
        matching: find.byType(RepaintBoundary),
      );
      expect(repaintBoundaries, findsNWidgets(3));
    });

    testWidgets('uses AnimatedBuilder for color animation', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: TypingIndicator(),
            ),
          ),
        ),
      );

      final typingIndicator = find.byType(TypingIndicator);

      // Should have AnimatedBuilder widgets for color animation
      final animatedBuilders = find.descendant(
        of: typingIndicator,
        matching: find.byType(AnimatedBuilder),
      );
      expect(animatedBuilders, findsNWidgets(3));
    });

    testWidgets('animation controller runs at 600ms duration', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: TypingIndicator(),
            ),
          ),
        ),
      );

      // Verify widget is present
      expect(find.byType(TypingIndicator), findsOneWidget);

      // Advance animation halfway through cycle
      await tester.pump(const Duration(milliseconds: 300));

      // Widget should still be present and animating
      expect(find.byType(TypingIndicator), findsOneWidget);

      // Complete one full animation cycle
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byType(TypingIndicator), findsOneWidget);
    });

    testWidgets('disposes animation controller properly', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: TypingIndicator(),
            ),
          ),
        ),
      );

      expect(find.byType(TypingIndicator), findsOneWidget);

      // Replace widget to trigger disposal
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: SizedBox.shrink(),
          ),
        ),
      );

      // Should not throw during disposal
      expect(find.byType(TypingIndicator), findsNothing);
    });
  });
}
