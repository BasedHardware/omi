import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import '../live_capture_controls.dart';

void main() {
  Future<List<String>> pump(WidgetTester tester, {required bool paused, bool canPause = true}) async {
    final calls = <String>[];
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 361,
          child: LiveCaptureControls(
            isPaused: paused,
            canPause: canPause,
            onPause: () => calls.add('pause'),
            onResume: () => calls.add('resume'),
            onEnd: () => calls.add('end'),
            pauseLabel: 'Pause',
            resumeLabel: 'Resume',
            endLabel: 'End',
            surface: const Color(0xFF1C2029),
            textColor: const Color(0xFFECEEF2),
            accent: const Color(0xFFECEEF2),
            onAccent: const Color(0xFF0A0C10),
            labelStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
          ),
        ),
      ),
    ));
    return calls;
  }

  testWidgets('running: Pause then End, equal widths, 44pt+ targets', (tester) async {
    final calls = await pump(tester, paused: false);
    expect(find.text('Pause'), findsOneWidget);
    expect(find.text('End'), findsOneWidget);
    final pause = tester.getSize(find.ancestor(of: find.text('Pause'), matching: find.byType(SizedBox)).first);
    final end = tester.getSize(find.ancestor(of: find.text('End'), matching: find.byType(SizedBox)).first);
    expect(pause.width, closeTo(end.width, 0.5));
    expect(pause.height, greaterThanOrEqualTo(44));
    await tester.tap(find.text('Pause'));
    await tester.tap(find.text('End'));
    expect(calls, ['pause', 'end']);
  });

  testWidgets('paused: shows Resume and calls resume', (tester) async {
    final calls = await pump(tester, paused: true);
    expect(find.text('Resume'), findsOneWidget);
    await tester.tap(find.text('Resume'));
    expect(calls, ['resume']);
  });

  testWidgets('device without pause: only End, full width', (tester) async {
    await pump(tester, paused: false, canPause: false);
    expect(find.text('Pause'), findsNothing);
    final end = tester.getSize(find.ancestor(of: find.text('End'), matching: find.byType(SizedBox)).first);
    expect(end.width, closeTo(361, 0.5));
  });
}
