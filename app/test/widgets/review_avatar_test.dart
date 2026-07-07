import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/apps/app_detail/widgets/review_avatar.dart';

Widget _wrap(Widget child) => MaterialApp(
  home: Scaffold(body: Center(child: child)),
);

void main() {
  group('ReviewAvatar', () {
    testWidgets('renders the uppercased first initial of the username', (tester) async {
      await tester.pumpWidget(_wrap(const ReviewAvatar(seed: 'uid_1', username: 'jane')));
      expect(find.text('J'), findsOneWidget);
    });

    testWidgets('falls back to "A" when the username is empty', (tester) async {
      await tester.pumpWidget(_wrap(const ReviewAvatar(seed: 'uid_1', username: '')));
      expect(find.text('A'), findsOneWidget);
    });

    testWidgets('makes no network calls (no Image widget in the tree)', (tester) async {
      // Regression: avatars previously came from a third-party service that, when
      // unreachable, hung forever and left a blank circle. The local avatar must
      // never reach the network.
      await tester.pumpWidget(_wrap(const ReviewAvatar(seed: 'uid_1', username: 'jane')));
      expect(find.byType(Image), findsNothing);
    });

    testWidgets('same seed yields a stable background color', (tester) async {
      Color bgOf(Finder f) => ((tester.widget<Container>(f).decoration) as BoxDecoration).color!;

      await tester.pumpWidget(_wrap(const ReviewAvatar(seed: 'uid_stable', username: 'jane')));
      final first = bgOf(find.byType(Container));

      await tester.pumpWidget(_wrap(const ReviewAvatar(seed: 'uid_stable', username: 'jane')));
      final second = bgOf(find.byType(Container));

      expect(first, second);
    });

    testWidgets('uses dark initials on a light background for contrast', (tester) async {
      // No foreground override + a light background must not render white initials.
      await tester.pumpWidget(
        _wrap(const ReviewAvatar(seed: 'uid_1', username: 'jane', backgroundColor: Color(0xFFFDCB6E))),
      );
      expect(tester.widget<Text>(find.text('J')).style!.color, const Color(0xFF1F1F25));
    });

    testWidgets('uses white initials on a dark background for contrast', (tester) async {
      await tester.pumpWidget(
        _wrap(const ReviewAvatar(seed: 'uid_1', username: 'jane', backgroundColor: Color(0xFF1F1F25))),
      );
      expect(tester.widget<Text>(find.text('J')).style!.color, Colors.white);
    });

    testWidgets('honors explicit background and foreground colors', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const ReviewAvatar(
            seed: 'uid_1',
            username: 'jane',
            backgroundColor: Color(0xFF112233),
            foregroundColor: Color(0xFF445566),
          ),
        ),
      );
      final container = tester.widget<Container>(find.byType(Container));
      expect((container.decoration as BoxDecoration).color, const Color(0xFF112233));
      expect(tester.widget<Text>(find.text('J')).style!.color, const Color(0xFF445566));
    });
  });
}
