import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/review.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/review/recent_changes_page.dart';
import 'package:omi/ui/ui.dart';
import '../../../integration_test/support/dream_changes_fixture.dart';
import '../../helpers/sfpro_font_fixtures.dart';
import '../../widgets/guided_voice_render_test.dart' show loadFonts;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    await loadFonts();
    for (final family in ['CupertinoSystemText', 'CupertinoSystemDisplay']) {
      final loader = FontLoader(family);
      for (final weight in ['REGULAR', 'MEDIUM', 'BOLD']) {
        loader.addFont(sfProFont('SFPRODISPLAY$weight.OTF'));
      }
      await loader.load();
    }
  });
  for (final scale in [1.0, 2.0]) {
    testWidgets('applied spelling shows before → after, speech in the sheet; Undo and Redo at $scale scale',
        (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      tester.view.physicalSize = Size(scale == 1 ? 786 : 640, 1704);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      OmiColors.active = OmiColors.forBrightness(Brightness.dark);
      final toggles = <bool>[];
      await tester.pumpWidget(MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildOmiTheme(brightness: Brightness.dark),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) =>
            MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)), child: child!),
        home: RecentChangesPage(
          loadChanges: ({cursor}) async => ApiSuccess(ReviewChangesPage(changes: [dreamSyntheticChange()])),
          setUndone: (id, {required undone}) async {
            expect(id, 'synthetic-spelling-change');
            toggles.add(undone);
            return ApiSuccess(dreamSyntheticChange(undone: undone));
          },
        ),
      ));
      await tester.pumpAndSettle();
      // A row without a server diff still shows the change itself, its source, and no raw id.
      expect(find.text('NAMES AND TERMS'), findsOneWidget);
      expect(find.text('UL'), findsOneWidget);
      expect(find.text('URL'), findsOneWidget);
      expect(find.textContaining('synthetic-launch'), findsNothing);
      expect(find.text('Spelling'), findsNothing);
      expect(tester.takeException(), isNull);
      final toggle = find.byKey(const ValueKey('recent_change_toggle_synthetic-spelling-change'));
      expect(toggle, findsOneWidget);
      await tester.ensureVisible(toggle);
      await tester.pumpAndSettle();
      await tester.tap(toggle);
      await tester.pumpAndSettle();
      expect(find.text('Redo'), findsOneWidget);
      await tester.tap(toggle);
      await tester.pumpAndSettle();
      expect(toggles, [true, false]);
      expect(find.text('Undo'), findsOneWidget);
      // The detail sheet shows the speech around the edit.
      await tester.tap(find.byKey(const ValueKey('recent_change_synthetic-spelling-change')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('recent_change_sheet')), findsOneWidget);
      expect(find.textContaining('Please send the'), findsOneWidget);
      expect(tester.takeException(), isNull);
      debugDefaultTargetPlatformOverride = null;
    });
  }
}
