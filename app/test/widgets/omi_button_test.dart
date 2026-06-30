import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/atoms/omi_button.dart';

/// The canonical primary CTA the app hand-rolls across onboarding. OmiButton's
/// primary variant must render an identical [ButtonStyle] so migrated call
/// sites are a 1:1 visual match.
ElevatedButton _legacyPrimary(VoidCallback onPressed, String label) => ElevatedButton(
      onPressed: onPressed,
      style: ElevatedButton.styleFrom(
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
        elevation: 0,
      ),
      child: Text(
        label,
        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
      ),
    );

void main() {
  void noop() {}
  const enabled = <WidgetState>{};

  group('OmiButton primary — 1:1 with legacy white CTA', () {
    testWidgets('resolves the same enabled-state ButtonStyle', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Column(
              children: [
                _legacyPrimary(noop, 'Continue'),
                OmiButton(label: 'Continue', onPressed: noop),
              ],
            ),
          ),
        ),
      );

      final buttons = find.byType(ElevatedButton);
      expect(buttons, findsNWidgets(2));

      final legacy = tester.widget<ElevatedButton>(buttons.at(0)).style!;
      final omi = tester.widget<ElevatedButton>(buttons.at(1)).style!;

      expect(omi.backgroundColor!.resolve(enabled), legacy.backgroundColor!.resolve(enabled));
      expect(omi.foregroundColor!.resolve(enabled), legacy.foregroundColor!.resolve(enabled));
      expect(omi.elevation!.resolve(enabled), legacy.elevation!.resolve(enabled));
      expect(omi.shape!.resolve(enabled), legacy.shape!.resolve(enabled));
    });

    testWidgets('label uses 18 / w600 / Manrope', (tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: OmiButton(label: 'Continue', onPressed: noop))),
      );

      final text = tester.widget<Text>(find.text('Continue'));
      expect(text.style!.fontSize, 18);
      expect(text.style!.fontWeight, FontWeight.w600);
      expect(text.style!.fontFamily, 'Manrope');
    });

    testWidgets('trailing icon renders after the label', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: OmiButton(
              label: 'Start Using Omi',
              onPressed: noop,
              icon: Icons.arrow_forward_rounded,
              trailingIcon: true,
            ),
          ),
        ),
      );

      final row = tester.widget<Row>(find.byType(Row));
      expect(row.children.length, 3);
      expect(row.children.first, isA<Text>());
      // Lock complete_screen's exact geometry: 8px gap, size-20 trailing icon.
      expect((row.children[1] as SizedBox).width, 8);
      final icon = row.children.last as Icon;
      expect(icon.icon, Icons.arrow_forward_rounded);
      expect(icon.size, 20);
    });
  });

  group('OmiButton primary — behavior', () {
    testWidgets('fires onPressed when enabled', (tester) async {
      var taps = 0;
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: OmiButton(label: 'Go', onPressed: () => taps++))),
      );
      await tester.tap(find.byType(OmiButton));
      expect(taps, 1);
    });

    testWidgets('isLoading shows a spinner and blocks taps', (tester) async {
      var taps = 0;
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: OmiButton(label: 'Go', isLoading: true, onPressed: () => taps++))),
      );
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      await tester.tap(find.byType(OmiButton), warnIfMissed: false);
      expect(taps, 0);
      expect(tester.widget<ElevatedButton>(find.byType(ElevatedButton)).onPressed, isNull);
    });

    testWidgets('enabled: false disables the button', (tester) async {
      await tester.pumpWidget(
        MaterialApp(home: Scaffold(body: OmiButton(label: 'Go', enabled: false, onPressed: noop))),
      );
      expect(tester.widget<ElevatedButton>(find.byType(ElevatedButton)).onPressed, isNull);
    });

    testWidgets('disabledColor/disabledTextColor override the disabled state', (tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            body: OmiButton(
              label: 'Go',
              onPressed: null,
              disabledColor: Color(0xFF111111),
              disabledTextColor: Color(0xFF222222),
            ),
          ),
        ),
      );
      final style = tester.widget<ElevatedButton>(find.byType(ElevatedButton)).style!;
      const disabled = <WidgetState>{WidgetState.disabled};
      expect(style.backgroundColor!.resolve(disabled), const Color(0xFF111111));
      expect(style.foregroundColor!.resolve(disabled), const Color(0xFF222222));
    });
  });
}
