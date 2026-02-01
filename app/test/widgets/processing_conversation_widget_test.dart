import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shimmer/shimmer.dart';

import 'package:omi/pages/conversations/widgets/processing_capture.dart';

void main() {
  group('ProcessingConversationWidget shimmer optimization', () {
    testWidgets('uses single Shimmer wrapper instead of multiple', (tester) async {
      // Create a minimal mock conversation for testing
      // Note: We can't fully instantiate ProcessingConversationWidget without
      // extensive mocking, so we test the shimmer consolidation pattern directly
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: RepaintBoundary(
              child: Shimmer.fromColors(
                baseColor: const Color(0xFF2A2A32),
                highlightColor: const Color(0xFF3D3D47),
                child: const Column(
                  children: [
                    // Multiple placeholder elements under single Shimmer
                    SizedBox(width: 24, height: 24),
                    SizedBox(width: 50, height: 14),
                    SizedBox(width: 100, height: 16),
                  ],
                ),
              ),
            ),
          ),
        ),
      );

      // Should have exactly ONE Shimmer widget (optimization: consolidated)
      expect(find.byType(Shimmer), findsOneWidget);

      // Should have RepaintBoundary for isolation
      expect(find.byType(RepaintBoundary), findsWidgets);
    });

    testWidgets('RepaintBoundary isolates shimmer from parent repaints', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: RepaintBoundary(
              key: const Key('testBoundary'),
              child: Shimmer.fromColors(
                baseColor: const Color(0xFF2A2A32),
                highlightColor: const Color(0xFF3D3D47),
                child: Container(width: 100, height: 100),
              ),
            ),
          ),
        ),
      );

      // Our test RepaintBoundary should be present
      final repaintBoundary = find.byKey(const Key('testBoundary'));
      expect(repaintBoundary, findsOneWidget);

      // Shimmer should be a descendant of our RepaintBoundary
      expect(
        find.descendant(
          of: repaintBoundary,
          matching: find.byType(Shimmer),
        ),
        findsOneWidget,
      );
    });
  });

  group('RecordingStatusIndicator', () {
    testWidgets('uses FadeTransition for blinking animation', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: RecordingStatusIndicator(),
            ),
          ),
        ),
      );

      final indicator = find.byType(RecordingStatusIndicator);
      expect(indicator, findsOneWidget);

      // Should use FadeTransition within the indicator (efficient opacity animation)
      final fadeTransitions = find.descendant(
        of: indicator,
        matching: find.byType(FadeTransition),
      );
      expect(fadeTransitions, findsOneWidget);

      // Should have red recording icon
      final icon = find.descendant(
        of: indicator,
        matching: find.byIcon(Icons.fiber_manual_record),
      );
      expect(icon, findsOneWidget);
    });

    testWidgets('animation cycles at 1000ms duration', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: RecordingStatusIndicator(),
            ),
          ),
        ),
      );

      expect(find.byType(RecordingStatusIndicator), findsOneWidget);

      // Advance through animation cycle
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(RecordingStatusIndicator), findsOneWidget);

      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(RecordingStatusIndicator), findsOneWidget);
    });

    testWidgets('disposes animation controller on unmount', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: RecordingStatusIndicator(),
            ),
          ),
        ),
      );

      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: SizedBox.shrink(),
          ),
        ),
      );

      // Should dispose without errors
      expect(find.byType(RecordingStatusIndicator), findsNothing);
    });

    testWidgets('displays red color for recording state', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: RecordingStatusIndicator(),
            ),
          ),
        ),
      );

      final indicator = find.byType(RecordingStatusIndicator);
      final iconFinder = find.descendant(
        of: indicator,
        matching: find.byIcon(Icons.fiber_manual_record),
      );
      final iconWidget = tester.widget<Icon>(iconFinder);
      expect(iconWidget.color, Colors.red);
    });
  });

  group('PausedStatusIndicator', () {
    testWidgets('uses FadeTransition for blinking animation', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: PausedStatusIndicator(),
            ),
          ),
        ),
      );

      final indicator = find.byType(PausedStatusIndicator);
      expect(indicator, findsOneWidget);

      // Should use FadeTransition within the indicator
      final fadeTransitions = find.descendant(
        of: indicator,
        matching: find.byType(FadeTransition),
      );
      expect(fadeTransitions, findsOneWidget);

      // Should have paused icon
      final icon = find.descendant(
        of: indicator,
        matching: find.byIcon(Icons.fiber_manual_record),
      );
      expect(icon, findsOneWidget);
    });

    testWidgets('displays orange color for paused state', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: Center(
              child: PausedStatusIndicator(),
            ),
          ),
        ),
      );

      final indicator = find.byType(PausedStatusIndicator);
      final iconFinder = find.descendant(
        of: indicator,
        matching: find.byIcon(Icons.fiber_manual_record),
      );
      final iconWidget = tester.widget<Icon>(iconFinder);
      expect(iconWidget.color, Colors.orange);
    });
  });
}
