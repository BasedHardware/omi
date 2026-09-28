import 'dart:ui' show Tristate;

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/ui.dart';

import 'ui_test_app.dart';

void main() {
  group('OmiIconButton', () {
    testWidgets('exposes its label as tooltip and semantics, with a 44pt target', (tester) async {
      final semantics = tester.ensureSemantics();
      var taps = 0;
      await pumpUi(
        tester,
        Scaffold(
          body: Center(
            child:
                OmiIconButton(icon: const Icon(Icons.share, size: 16), label: 'Share memory', onPressed: () => taps++),
          ),
        ),
      );
      expect(find.byTooltip('Share memory'), findsOneWidget);
      expect(tester.getSize(find.byType(OmiIconButton)), const Size(kOmiMinTapTarget, kOmiMinTapTarget));
      final data = tester.getSemantics(find.bySemanticsLabel('Share memory')).getSemanticsData();
      expect(data.flagsCollection.isButton, isTrue);
      expect(data.hasAction(SemanticsAction.tap), isTrue);

      final rect = tester.getRect(find.byType(OmiIconButton));
      await tester.tapAt(rect.bottomRight - const Offset(2, 2));
      expect(taps, 1);
      semantics.dispose();
    });

    testWidgets('a null onPressed is announced as disabled', (tester) async {
      final semantics = tester.ensureSemantics();
      await pumpUi(
        tester,
        const Scaffold(body: OmiIconButton(icon: Icon(Icons.delete), label: 'Delete', onPressed: null)),
      );
      final data = tester.getSemantics(find.bySemanticsLabel('Delete')).getSemanticsData();
      expect(data.flagsCollection.isEnabled, isNot(Tristate.isTrue));
      expect(data.hasAction(SemanticsAction.tap), isFalse);
      semantics.dispose();
    });
  });

  group('showOmiSheet', () {
    Future<Future<String?>> openSheet(WidgetTester tester) async {
      late Future<String?> result;
      await pumpUi(
        tester,
        Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () {
                result = showOmiSheet<String>(
                  context: context,
                  title: 'Move to Folder',
                  builder: (sheetContext) => TextButton(
                    onPressed: () => Navigator.of(sheetContext).pop('work'),
                    child: const Text('Work'),
                  ),
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      return result;
    }

    testWidgets('renders the drag handle, the title and a trailing close button', (tester) async {
      await openSheet(tester);
      expect(find.text('Move to Folder'), findsOneWidget);
      expect(find.byType(OmiCloseButton), findsOneWidget);
      // The framework drag handle announces the localized dismiss action.
      expect(find.bySemanticsLabel('Dismiss'), findsOneWidget);

      final title = tester.getRect(find.text('Move to Folder'));
      final close = tester.getRect(find.byType(OmiCloseButton));
      expect(close.left, greaterThanOrEqualTo(title.right), reason: 'the close X is trailing');
      final sheet = tester.widget<BottomSheet>(find.byType(BottomSheet));
      expect(sheet.showDragHandle, isTrue);
      expect(sheet.backgroundColor, OmiColors.surface1);
    });

    testWidgets('closes on X with a null result', (tester) async {
      final result = await openSheet(tester);
      await tester.tap(find.byType(OmiCloseButton));
      await tester.pumpAndSettle();
      expect(find.text('Move to Folder'), findsNothing);
      expect(await result, isNull);
    });

    testWidgets('returns the value the content pops with', (tester) async {
      final result = await openSheet(tester);
      await tester.tap(find.text('Work'));
      await tester.pumpAndSettle();
      expect(await result, 'work');
    });
  });

  group('page states', () {
    testWidgets('OmiErrorState shows Try Again and calls retry', (tester) async {
      var retries = 0;
      await pumpUi(
        tester,
        Scaffold(
            body: OmiErrorState(
                title: "Couldn't Load Tasks", message: 'Check your connection.', onRetry: () => retries++)),
      );
      expect(find.text("Couldn't Load Tasks"), findsOneWidget);
      expect(find.text('Check your connection.'), findsOneWidget);
      await tester.tap(find.text('Try Again'));
      await tester.pump();
      expect(retries, 1);
    });

    testWidgets('OmiEmptyState renders title, message and action', (tester) async {
      var tapped = false;
      await pumpUi(
        tester,
        Scaffold(
          body: OmiEmptyState(
            icon: Icons.search_off,
            title: 'No Matching Memories',
            message: 'Try a different search.',
            action: OmiButton.secondary(
              label: 'Clear Search',
              size: OmiButtonSize.compact,
              onPressed: () => tapped = true,
            ),
          ),
        ),
      );
      expect(find.text('No Matching Memories'), findsOneWidget);
      expect(find.text('Try a different search.'), findsOneWidget);
      await tester.tap(find.text('Clear Search'));
      expect(tapped, isTrue);
    });

    testWidgets('OmiEmptyState draws a non-Material glyph at the empty-state size', (tester) async {
      await pumpUi(
        tester,
        const Scaffold(body: OmiEmptyState(glyph: FaIcon(FontAwesomeIcons.key), title: 'No API Keys')),
      );
      final glyph = find.byType(FaIcon);
      expect(glyph, findsOneWidget);
      expect(tester.getSize(glyph).height, 40);
      expect(find.byType(Icon), findsNothing);
    });

    testWidgets('OmiLoadingState shows one white spinner and its label', (tester) async {
      await pumpUi(tester, const Scaffold(body: OmiLoadingState(label: 'Loading tasks…')));
      final indicator = tester.widget<CircularProgressIndicator>(find.byType(CircularProgressIndicator));
      expect(indicator.color, OmiColors.accent);
      expect(find.text('Loading tasks…'), findsOneWidget);
    });
  });

  group('settings', () {
    testWidgets('a toggle row flips from anywhere on the row and announces its state', (tester) async {
      final semantics = tester.ensureSemantics();
      var value = false;
      await pumpUi(
        tester,
        Scaffold(
          body: StatefulBuilder(
            builder: (context, setState) => OmiSettingsGroup(
              children: [
                OmiSettingsRow.toggle(
                  title: 'Auto Sync',
                  subtitle: 'Upload recordings when on Wi-Fi',
                  value: value,
                  onChanged: (v) => setState(() => value = v),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.tap(find.text('Auto Sync'));
      await tester.pump();
      expect(value, isTrue);
      final data = tester.getSemantics(find.byType(OmiSettingsRow)).getSemanticsData();
      expect(data.flagsCollection.isToggled, Tristate.isTrue);
      expect(data.label, contains('Auto Sync'));
      semantics.dispose();
    });

    testWidgets('a navigation row is at least 48pt, shows a chevron and its value', (tester) async {
      var taps = 0;
      await pumpUi(
        tester,
        Scaffold(
          body: OmiSettingsGroup(
            header: 'Account',
            children: [
              OmiSettingsRow(
                leading: const Icon(Icons.language),
                title: 'Language',
                value: 'English',
                onTap: () => taps++,
              ),
              const OmiSettingsRow(title: 'Version', value: '1.0.0'),
            ],
          ),
        ),
      );
      expect(find.text('Account'), findsOneWidget);
      expect(tester.getSize(find.byType(OmiSettingsRow).first).height, greaterThanOrEqualTo(48));
      expect(find.byIcon(Icons.chevron_right), findsOneWidget, reason: 'only the tappable row has a chevron');
      await tester.tap(find.text('English'));
      expect(taps, 1);
    });

    testWidgets('OmiSwitch is a Cupertino switch on iOS and a Material switch on Android', (tester) async {
      await pumpUi(tester, Scaffold(body: OmiSwitch(value: true, onChanged: (_) {})), platform: TargetPlatform.iOS);
      expect(find.byType(Switch), findsNothing);
      await pumpUi(tester, Scaffold(body: OmiSwitch(value: true, onChanged: (_) {})), platform: TargetPlatform.android);
      await tester.pumpAndSettle(); // the theme animates to the new platform
      expect(find.byType(Switch), findsOneWidget);
    });
  });

  testWidgets('OmiSearchField shows a labelled clear button only when there is text', (tester) async {
    var cleared = 0;
    final changes = <String>[];
    await pumpUi(
      tester,
      Scaffold(
        body: OmiSearchField(placeholder: 'Search memories', onChanged: changes.add, onCleared: () => cleared++),
      ),
    );
    expect(find.text('Search memories'), findsOneWidget);
    expect(find.byTooltip('Clear Search'), findsNothing);

    await tester.enterText(find.byType(TextField), 'coffee');
    await tester.pump();
    expect(find.byTooltip('Clear Search'), findsOneWidget);

    await tester.tap(find.byTooltip('Clear Search'));
    await tester.pump();
    expect(find.text('coffee'), findsNothing);
    expect(changes.last, '');
    expect(cleared, 1);
    expect(find.byTooltip('Clear Search'), findsNothing);
  });
}
