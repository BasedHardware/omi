import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/ui/atoms/omi_button.dart';

/// The canonical primary CTA the app hand-rolls across onboarding. OmiButton's
/// primary variant must render an identical [ButtonStyle] so migrated call
/// sites are a 1:1 visual match.
ElevatedButton _legacyPrimary(VoidCallback onPressed, String label, {double radius = 28, double fontSize = 18}) =>
    ElevatedButton(
      onPressed: onPressed,
      style: ElevatedButton.styleFrom(
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius)),
        elevation: 0,
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: fontSize, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
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

    // The migrated call sites use three geometries: onboarding (28/18),
    // settings (14/16), announcement (26/16). Assert each maps 1:1.
    for (final g in const [
      (radius: 28.0, fontSize: 18.0),
      (radius: 14.0, fontSize: 16.0),
      (radius: 26.0, fontSize: 16.0),
    ]) {
      testWidgets('matches legacy ButtonStyle at radius ${g.radius} / fontSize ${g.fontSize}', (tester) async {
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: Column(
                children: [
                  _legacyPrimary(noop, 'Continue', radius: g.radius, fontSize: g.fontSize),
                  OmiButton(label: 'Continue', onPressed: noop, borderRadius: g.radius, fontSize: g.fontSize),
                ],
              ),
            ),
          ),
        );

        final buttons = find.byType(ElevatedButton);
        final legacy = tester.widget<ElevatedButton>(buttons.at(0)).style!;
        final omi = tester.widget<ElevatedButton>(buttons.at(1)).style!;
        expect(omi.shape!.resolve(enabled), legacy.shape!.resolve(enabled));

        final legacyText = tester.widget<Text>(find.descendant(of: buttons.at(0), matching: find.byType(Text)));
        final omiText = tester.widget<Text>(find.descendant(of: buttons.at(1), matching: find.byType(Text)));
        expect(omiText.style!.fontSize, legacyText.style!.fontSize);
        expect(omiText.style!.fontWeight, legacyText.style!.fontWeight);
      });
    }

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

    testWidgets('fontWeight / iconSize / iconGap / padding overrides propagate', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: OmiButton(
              label: 'Go',
              onPressed: noop,
              icon: Icons.add,
              iconSize: 24,
              iconGap: 10,
              fontWeight: FontWeight.w500,
              padding: const EdgeInsets.symmetric(horizontal: 16),
            ),
          ),
        ),
      );

      expect(tester.widget<Text>(find.text('Go')).style!.fontWeight, FontWeight.w500);
      expect(tester.widget<Icon>(find.byType(Icon)).size, 24);
      final row = tester.widget<Row>(find.byType(Row));
      expect((row.children[1] as SizedBox).width, 10);
      final style = tester.widget<ElevatedButton>(find.byType(ElevatedButton)).style!;
      expect(style.padding!.resolve(<WidgetState>{}), const EdgeInsets.symmetric(horizontal: 16));
    });
  });
}
