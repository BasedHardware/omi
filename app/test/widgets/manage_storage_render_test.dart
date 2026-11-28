import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/offline_sync_storage_sheet.dart';
import 'package:omi/pages/conversations/widgets/storage_clear_flow.dart';
import 'package:omi/services/wals/storage_clear.dart';
import 'package:omi/ui/ui.dart';

import '../helpers/sfpro_font_fixtures.dart';

/// Renders Manage Storage on an iPhone-sized screen with the app's real fonts and asserts each
/// state lays out without overflow. With `--dart-define=MANAGE_STORAGE_RENDER_OUTPUT=<dir>` it
/// also writes the PNGs used as PR evidence. Amounts are synthetic, shaped like the report that
/// prompted the change (tens of thousands of ~1 min files; 11 h still on the pendant).
Future<void> _loadFonts() async {
  final manifest = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List;
  for (final family in manifest) {
    final loader = FontLoader(family['family'] as String);
    for (final font in family['fonts'] as List) {
      loader.addFont(rootBundle.load(font['asset'] as String));
    }
    await loader.load();
  }
  for (final family in [
    '.SF UI Text',
    '.SF UI Display',
    '.SF Pro Text',
    '.SF Pro Display',
    'SF Pro Display',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    'FlutterTest',
    'Roboto'
  ]) {
    final loader = FontLoader(family);
    for (final font in ['REGULAR', 'MEDIUM', 'BOLD']) {
      loader.addFont(sfProFont('SFPRODISPLAY$font.OTF'));
    }
    await loader.load();
  }
}

const _amounts = StorageAmounts(
  uploadedSeconds: 440 * 3600,
  uploadedCount: 26589,
  phonePendingSeconds: 71 * 3600,
  devicePendingSeconds: 11 * 3600,
  pendingCount: 4937,
  allCount: 31526,
  allSeconds: 522 * 3600,
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(_loadFonts);
  const output = String.fromEnvironment('MANAGE_STORAGE_RENDER_OUTPUT');
  final boundary = GlobalKey();

  Future<void> writeFrame(WidgetTester tester, String name) async {
    expect(tester.takeException(), isNull);
    if (output.isEmpty) return;
    await tester.runAsync(() async {
      final render = boundary.currentContext!.findRenderObject()! as RenderRepaintBoundary;
      final image = await render.toImage(pixelRatio: 3);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(output).create(recursive: true);
      await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
    });
  }

  Future<void> pumpSheet(WidgetTester tester, Widget sheet,
      {String? title,
      bool closable = true,
      Color Function()? surface,
      EdgeInsets? padding,
      Brightness brightness = Brightness.dark}) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    tester.view.physicalSize = const Size(393, 852);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final previous = OmiColors.active;
    OmiColors.active = OmiColors.forBrightness(brightness);
    addTearDown(() => OmiColors.active = previous);
    await tester.pumpWidget(RepaintBoundary(
      key: boundary,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildOmiTheme(brightness: brightness),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          backgroundColor: OmiColors.surface0,
          body: Align(
            alignment: Alignment.bottomCenter,
            child: Material(
              color: (surface ?? () => OmiColors.surface1)(),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
              child: OmiSheetScaffold(
                title: title,
                showCloseButton: closable,
                padding:
                    padding ?? const EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xs, OmiSpacing.xl, OmiSpacing.xl),
                child: sheet,
              ),
            ),
          ),
        ),
      ),
    ));
    await tester.pump();
  }

  for (final (slug, brightness) in [
    ('001-mobile-ios-manage-storage-hours', Brightness.dark),
    ('005-mobile-ios-manage-storage-light', Brightness.light),
  ]) {
    testWidgets('Manage Storage shows hours of audio and where it waits ($brightness)', (tester) async {
      await pumpSheet(
        tester,
        Builder(
          builder: (context) => OfflineSyncStorageSheet(
            amounts: _amounts,
            onFreeUpSpace: () {},
            onDeletePending: () {},
            onDeleteAll: () {},
            // As on the Auto Sync page.
            footer: OmiSettingsRow.toggle(
              leading: const Icon(Icons.auto_delete_outlined),
              title: AppLocalizations.of(context).autoRemoveSyncedCopiesTitle,
              subtitle: AppLocalizations.of(context).autoRemoveSyncedCopiesDays(7),
              value: true,
              onChanged: (_) {},
            ),
          ),
        ),
        title: 'Manage Storage',
        // As showOfflineSyncStorageSheet opens it.
        surface: () => OmiColors.surface0,
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, OmiSpacing.xl),
        brightness: brightness,
      );
      expect(find.text('440h'), findsOneWidget);
      expect(find.text('On this phone 71h · On your Omi 11h'), findsOneWidget);
      await writeFrame(tester, slug);
      debugDefaultTargetPlatformOverride = null;
    });
  }

  testWidgets('deleting not-uploaded audio confirms the hours and that sync pauses', (tester) async {
    await pumpSheet(tester, const SizedBox(height: 200));
    final context = tester.element(find.byType(SizedBox).last);
    final l = AppLocalizations.of(context);
    showDialog<void>(
      context: context,
      builder: (_) => OmiAlertDialog(
        title: l.storageDeletePendingTitle(OmiDuration.compact(_amounts.pendingSeconds, l)),
        message: l.storageDeletePendingMessage,
        actions: [
          OmiDialogAction(label: l.cancel, onPressed: () {}, isDefault: true),
          OmiDialogAction(label: l.delete, onPressed: () {}, isDestructive: true),
        ],
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Delete 82h of audio?'), findsOneWidget);
    await writeFrame(tester, '002-mobile-ios-delete-pending-confirm');
    debugDefaultTargetPlatformOverride = null;
  });

  for (final (slug, progress) in [
    ('003-mobile-ios-clear-stopping-sync', const StorageClearProgress(StorageClearPhase.stopping)),
    (
      '004-mobile-ios-clear-deleting-progress',
      const StorageClearProgress(StorageClearPhase.deleting, done: 1240, total: 4937)
    ),
  ]) {
    testWidgets('clear progress: ${progress.phase.name}', (tester) async {
      final notifier = ValueNotifier(progress);
      addTearDown(notifier.dispose);
      // The real progress sheet cannot be dismissed, so it has no close button.
      await pumpSheet(tester, StorageClearProgressView(progress: notifier), closable: false);
      await tester.pump(const Duration(milliseconds: 300));
      if (progress.phase == StorageClearPhase.deleting) {
        expect(find.text('Deleting… 1,240 / 4,937'), findsWidgets);
      } else {
        expect(find.text('Stopping sync…'), findsWidgets);
      }
      await writeFrame(tester, slug);
      debugDefaultTargetPlatformOverride = null;
    });
  }
}
