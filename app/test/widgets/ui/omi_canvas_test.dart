/// The canvas (Home, Tasks and the conversation page): a white page with grouped-grey cards in light
/// mode, the usual surfaces in dark, glass for the controls floating on it, and device tiles at the
/// start of its rows. Every other screen keeps the grouped look.
library;

import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/device_tile.dart';
import 'package:omi/widgets/header_circle_button.dart';

void main() {
  tearDown(() => OmiColors.active = OmiPalette.light);

  Future<BuildContext> pumpIn(WidgetTester tester, Widget child, {bool canvas = true}) async {
    late BuildContext inner;
    final probe = Builder(builder: (context) {
      inner = context;
      return child;
    });
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: Center(child: canvas ? OmiCanvas(child: probe) : probe))));
    return inner;
  }

  group('OmiCanvas', () {
    testWidgets('light: a white page with grouped-grey cards; off the canvas, the grouped look', (tester) async {
      var context = await pumpIn(tester, const SizedBox());
      expect(OmiCanvas.isOn(context), isTrue);
      expect(OmiCanvas.pageOf(context), const Color(0xFFFFFFFF));
      expect(OmiCanvas.cardOf(context), const Color(0xFFF2F2F7));

      context = await pumpIn(tester, const SizedBox(), canvas: false);
      expect(OmiCanvas.isOn(context), isFalse);
      expect(OmiCanvas.pageOf(context), OmiColors.surface0);
      expect(OmiCanvas.cardOf(context), OmiColors.surface1);
    });

    testWidgets('dark: the canvas is the usual page and card, so dark screens do not change', (tester) async {
      OmiColors.active = OmiPalette.dark;
      final context = await pumpIn(tester, const SizedBox());
      expect(OmiCanvas.pageOf(context), OmiColors.surface0);
      expect(OmiCanvas.cardOf(context), OmiColors.surface1);
    });

    testWidgets('the search field is the card colour: visible on the white page, unchanged in dark', (tester) async {
      Color fill() => tester.widget<TextField>(find.byType(TextField)).decoration!.fillColor!;
      await pumpIn(tester, const OmiSearchField(placeholder: 'Search'));
      expect(fill(), OmiColors.canvasCard);

      OmiColors.active = OmiPalette.dark;
      await pumpIn(tester, const OmiSearchField(placeholder: 'Search'));
      expect(fill(), OmiColors.surface1, reason: 'the Tasks search bar in dark mode stays as it is');
    });
  });

  group('OmiGlass', () {
    testWidgets('a translucent fill and a lit rim; blur only when asked', (tester) async {
      await pumpIn(tester, const OmiGlass(shape: StadiumBorder(), child: SizedBox(width: 120, height: 40)));
      final boxes = tester.widgetList<DecoratedBox>(find.byType(DecoratedBox)).toList();
      expect(boxes.map((b) => b.decoration), contains(OmiGlass.fill(const StadiumBorder())));
      expect(
          boxes.where((b) => b.decoration is OmiGlassRim && b.position == DecorationPosition.foreground), hasLength(1));
      expect(find.byType(BackdropFilter), findsNothing);

      await pumpIn(tester, const OmiGlass(shape: StadiumBorder(), blur: true, child: SizedBox(width: 120, height: 40)));
      expect(find.byType(BackdropFilter), findsOneWidget);
      expect(find.byType(ClipPath), findsOneWidget, reason: 'the blur stays inside the shape');
      final shadow = tester
          .widget<DecoratedBox>(find.ancestor(of: find.byType(ClipPath), matching: find.byType(DecoratedBox)).first);
      expect((shadow.decoration as ShapeDecoration).shadows, OmiGlass.floatShadows,
          reason: 'painted outside the clip, so the blur does not cut it off');
    });

    test('light glass follows Omi v8: hairline circles, a frosted floating bar; dark is as it was', () {
      expect(OmiColors.glass, const Color(0x8CFFFFFF));
      expect(OmiColors.glassEdge, const Color(0x17000000));
      expect(OmiColors.glassRim, const Color(0x17000000), reason: 'one even hairline round a circle');
      expect(OmiGlass.shadows, hasLength(1), reason: 'a touch of lift');
      expect(OmiGlass.shadows!.single.blurRadius, lessThanOrEqualTo(12), reason: 'close under it, no haze');
      expect(OmiGlass.fill(const CircleBorder()).shadows, OmiGlass.shadows);
      expect(OmiColors.floatGlass, const Color(0x9EFFFFFF));
      expect(OmiGlass.floatShadows, hasLength(2), reason: 'a faint outline and a soft shadow');

      OmiColors.active = OmiPalette.dark;
      expect(OmiColors.glass, const Color(0x803A3A3C));
      expect(OmiColors.glassEdge, const Color(0x29FFFFFF));
      expect(OmiColors.floatGlass, OmiColors.glass, reason: 'the floating bar is the same glass in dark');
      expect(OmiGlass.floatShadows, isEmpty, reason: 'dark is unchanged');
      expect(OmiGlass.shadows, isNull);
    });

    test('a tint replaces the glass fill; the rim follows the palette', () {
      expect(OmiGlass.fill(const CircleBorder(), tint: Colors.red).color, Colors.red);
      expect(OmiGlass.fill(const CircleBorder()).color, OmiColors.glass);
      OmiColors.active = OmiPalette.dark;
      expect(OmiGlass.rim(const CircleBorder()),
          OmiGlassRim(shape: const CircleBorder(), edge: OmiColors.glassEdge, rim: OmiColors.glassRim));
    });
  });

  group('filled icon circles', () {
    Container circle(WidgetTester tester) =>
        tester.widget<Container>(find.descendant(of: find.byType(OmiIconButton), matching: find.byType(Container)));

    testWidgets('are glass on the canvas and keep their fill elsewhere', (tester) async {
      final button = OmiIconButton.filled(icon: const Icon(Icons.search), label: 'Search', onPressed: () {});
      await pumpIn(tester, button);
      expect(circle(tester).decoration, OmiGlass.fill(const CircleBorder()));
      expect(circle(tester).foregroundDecoration, isA<OmiGlassRim>());

      await pumpIn(tester, button, canvas: false);
      expect((circle(tester).decoration! as BoxDecoration).color, OmiColors.surface1);
      expect(circle(tester).foregroundDecoration, isNull);
    });

    testWidgets('a header circle that is on tints the glass; its badge is ringed in the page colour', (tester) async {
      await pumpIn(
        tester,
        HeaderCircleButton(
          icon: const Icon(Icons.cloud),
          semanticLabel: 'Sync',
          color: OmiColors.surface3,
          badgeCount: 2,
          onTap: () {},
        ),
      );
      expect(circle(tester).decoration, OmiGlass.fill(const CircleBorder(), tint: OmiColors.surface3));
      final badge = tester.widget<Container>(find.byKey(const ValueKey('header_count_badge')));
      expect(((badge.decoration! as BoxDecoration).border! as Border).top.color, OmiColors.canvas);
    });
  });

  testWidgets('a locked row is veiled in the page colour on the canvas, in the card colour elsewhere', (tester) async {
    Color veil() => tester.widget<ColoredBox>(find.byKey(const Key('locked_preview_tint'))).color;
    final locked = OmiLockedPreview(label: 'Upgrade', onPressed: () {}, child: const SizedBox(width: 200, height: 60));
    await pumpIn(tester, locked);
    expect(veil(), OmiColors.canvas.withValues(alpha: 0.65));
    await pumpIn(tester, locked, canvas: false);
    expect(veil(), OmiColors.surface1.withValues(alpha: 0.65));
  });

  group('DeviceTile', () {
    test('every source has a drawn glyph; one with no device of its own gets the conversation bubble', () {
      for (final source in ['omi', 'friend', 'limitless', 'bee', 'plaud']) {
        expect(DeviceTile.glyphFor(source), DeviceTile.glyphFor('omi'), reason: source);
      }
      expect(DeviceTile.glyphFor('phone'), isNotNull);
      expect(DeviceTile.glyphFor('apple_watch'), isNotNull);
      expect(DeviceTile.glyphFor('openglass'), DeviceTile.glyphFor('rayban_meta'));
      expect(
          {DeviceTile.glyphFor('omi'), DeviceTile.glyphFor('phone'), DeviceTile.glyphFor('apple_watch')}, hasLength(3));
      expect(DeviceTile.glyphFor('screenpipe'), DeviceTile.glyphFor('desktop'));
      expect(DeviceTile.glyphFor('workflow'), isNot(DeviceTile.glyphFor(null)));
      // An older row (no source) and an unknown one share the bubble, never a bare mic icon.
      expect(DeviceTile.glyphFor('xor'), DeviceTile.glyphFor(null));
      for (final source in ConversationSource.values) {
        expect(DeviceTile.glyphFor(source.name), isNotEmpty, reason: source.name);
      }
    });

    testWidgets('a 40pt warm tile with the glyph; decorative', (tester) async {
      await pumpIn(tester, const DeviceTile(source: 'omi'));
      expect(tester.getSize(find.byType(DeviceTile)), const Size.square(DeviceTile.size));
      expect(find.byType(SvgPicture), findsOneWidget);
      final tile =
          tester.widget<Container>(find.descendant(of: find.byType(DeviceTile), matching: find.byType(Container)));
      expect((tile.decoration! as BoxDecoration).color, OmiColors.deviceTile);
      expect((tile.decoration! as BoxDecoration).border, isNull, reason: 'no outline: a mark, not a button');
      expect(find.descendant(of: find.byType(DeviceTile), matching: find.byType(ExcludeSemantics)), findsOneWidget);

      // Every source draws its glyph; only a caller's own icon shows an Icon.
      await pumpIn(tester, const DeviceTile(source: 'screenpipe'));
      expect(find.byType(SvgPicture), findsOneWidget);
      await pumpIn(tester, const DeviceTile(icon: Icons.call_rounded));
      expect(find.byType(SvgPicture), findsNothing);
      expect(find.byType(Icon), findsOneWidget);
    });

    testWidgets('a recap tile holds its emoji', (tester) async {
      await pumpIn(tester, const DeviceTile(emoji: '🌉', source: 'omi'));
      expect(find.text('🌉'), findsOneWidget);
      expect(find.byType(SvgPicture), findsNothing);
    });

    testWidgets('missing is an empty dashed outline; faded dims it; a status dot is ringed in the page colour',
        (tester) async {
      await pumpIn(tester, const DeviceTile(icon: Icons.event_busy, missing: true));
      final tile =
          tester.widget<Container>(find.descendant(of: find.byType(DeviceTile), matching: find.byType(Container)));
      expect(tile.decoration, isNull);
      expect(find.descendant(of: find.byType(DeviceTile), matching: find.byType(CustomPaint)), findsWidgets);

      await pumpIn(tester, const DeviceTile(source: 'omi', faded: true));
      expect(tester.widget<Opacity>(find.byType(Opacity)).opacity, 0.45);

      await pumpIn(tester, DeviceTile(source: 'phone', status: OmiColors.success));
      final dot = tester.widget<Container>(find.byKey(const ValueKey('device_tile_status')));
      final ring = (dot.decoration! as BoxDecoration).border! as Border;
      expect((dot.decoration! as BoxDecoration).color, OmiColors.success);
      expect(ring.top.color, OmiColors.canvas);
    });
  });
}
