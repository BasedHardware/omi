// Design-render harness for the delete-account flow changes (local only, gitignored).
//
// Pumps the real DeleteAccount flow inside the real Omi theme at 393x932 logical @3x with an
// iOS platform override, real SF Pro text, real icon fonts, and rasterizes the tree to PNGs in
// /Volumes/Ephemeral/scratch/deletion-renders/.
//
//   nice flutter test --no-pub .local/render_delete_flow_test.dart
@TestOn('mac-os')
library;

import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/delete_account.dart';
import 'package:omi/pages/settings/restore_account.dart';
import 'package:omi/backend/http/api/account_deletion.dart';
import 'package:omi/ui/omi_theme.dart';
import 'package:omi/ui/omi_tokens.dart';

const outDir = '/Volumes/Ephemeral/scratch/deletion-renders/v2';
const width = 393.0;
const height = 932.0;
const dpr = 3.0;
// iPhone 15-class insets so the app bar and the bottom action area sit where they do on device.
const topInset = 59.0;
const bottomInset = 34.0;

Future<void> _loadFamily(String family, String path) async {
  final bytes = File(path).readAsBytesSync();
  final loader = FontLoader(family)..addFont(Future.value(ByteData.view(bytes.buffer)));
  await loader.load();
}

String _packageRoot(String package) {
  final config = jsonDecode(File('.dart_tool/package_config.json').readAsStringSync()) as Map<String, dynamic>;
  for (final entry in config['packages'] as List<dynamic>) {
    if (entry['name'] == package) return Uri.parse(entry['rootUri'] as String).toFilePath();
  }
  throw StateError('package $package not found');
}

String get _flutterRoot {
  // flutter_tester lives at <root>/bin/cache/artifacts/engine/<host>/flutter_tester.
  final exe = Platform.resolvedExecutable;
  return exe.substring(0, exe.indexOf('/bin/cache/'));
}

Future<void> _loadFonts() async {
  final sf = '/System/Library/Fonts/SFNS.ttf';
  for (final family in [
    'Roboto',
    'CupertinoSystemText',
    'CupertinoSystemDisplay',
    '.SF UI Text',
    '.SF UI Display',
    'FlutterTest',
  ]) {
    await _loadFamily(family, sf);
  }
  await _loadFamily('MaterialIcons', '$_flutterRoot/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf');
  final faRoot = _packageRoot('font_awesome_flutter');
  for (final entry in {
    'FontAwesomeSolid': 'Font-Awesome-7-Free-Solid-900.otf',
    'FontAwesomeRegular': 'Font-Awesome-7-Free-Regular-400.otf',
    'FontAwesomeBrands': 'Font-Awesome-7-Brands-Regular-400.otf',
  }.entries) {
    await _loadFamily(entry.key, '$faRoot/lib/fonts/${entry.value}');
    await _loadFamily('packages/font_awesome_flutter/${entry.key}', '$faRoot/lib/fonts/${entry.value}');
  }
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    await _loadFonts();
  });

  Widget host(Brightness brightness, Widget home) {
    OmiColors.active = OmiColors.forBrightness(brightness);
    return RepaintBoundary(
      key: const ValueKey('render_root'),
      child: MaterialApp(
        theme: buildOmiTheme(brightness: brightness),
        debugShowCheckedModeBanner: false,
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [Locale('en')],
        home: home,
      ),
    );
  }

  Future<void> pumpDevice(WidgetTester tester, Brightness brightness, Widget home) async {
    tester.view.physicalSize = Size(width * dpr, height * dpr);
    tester.view.devicePixelRatio = dpr;
    tester.view.padding = FakeViewPadding(left: 0, top: topInset * dpr, right: 0, bottom: bottomInset * dpr);
    addTearDown(tester.view.reset);
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    await tester.pumpWidget(host(brightness, home));
    await tester.pumpAndSettle();
  }

  Future<void> capture(WidgetTester tester, String name) async {
    await tester.runAsync(() async {
      final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(const ValueKey('render_root')));
      final image = await boundary.toImage(pixelRatio: dpr);
      final data = (await image.toByteData(format: ui.ImageByteFormat.png))!;
      Directory(outDir).createSync(recursive: true);
      File('$outDir/$name.png').writeAsBytesSync(data.buffer.asUint8List());
      image.dispose();
    });
  }

  /// Reason (non-pause-eligible) → feedback → confirm, with DELETE typed.
  Future<void> reachConfirmStep(WidgetTester tester, Brightness brightness, DeletionPendingData data) async {
    await pumpDevice(tester, brightness, DeleteAccount(loadPendingData: () async => data));
    await tester.tap(find.text('Privacy concerns'));
    await tester.pump();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Continue'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('delete_account_confirm_field')), 'DELETE');
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pumpAndSettle();
    expect(find.text('Delete Your Account?'), findsOneWidget);
  }

  for (final brightness in [Brightness.light, Brightness.dark]) {
    final mode = brightness.name;

    testWidgets('A: confirm step with held recordings ($mode)', (tester) async {
      try {
        const data = DeletionPendingData(processingCount: 14, notUploadedCount: 3, gracePeriodDays: 14);
        await reachConfirmStep(tester, brightness, data);
        expect(find.textContaining('14 recordings are still processing'), findsOneWidget);
        expect(find.textContaining("3 recordings haven't uploaded yet"), findsOneWidget);
        await capture(tester, 'a_held_$mode');
      } finally {
        debugDefaultTargetPlatformOverride = null;
      }
    });

    testWidgets('A: confirm step with nothing pending ($mode)', (tester) async {
      try {
        const data = DeletionPendingData(processingCount: 0, notUploadedCount: 0, gracePeriodDays: 14);
        await reachConfirmStep(tester, brightness, data);
        expect(find.textContaining('still processing'), findsNothing);
        expect(find.textContaining('haven’t uploaded yet'), findsNothing);
        expect(find.textContaining('Sign in again within 14 days'), findsOneWidget);
        await capture(tester, 'a_none_$mode');
      } finally {
        debugDefaultTargetPlatformOverride = null;
      }
    });

    for (final entry in {
      'a_immediate': const DeletionPendingData(processingCount: 14, notUploadedCount: 3, gracePeriodDays: 0),
      'a_server_only': const DeletionPendingData(processingCount: 14, notUploadedCount: 0, gracePeriodDays: 14),
      'a_phone_only': const DeletionPendingData(processingCount: 0, notUploadedCount: 3, gracePeriodDays: 7),
    }.entries) {
      testWidgets('${entry.key} ($mode)', (tester) async {
        try {
          await reachConfirmStep(tester, brightness, entry.value);
          await capture(tester, '${entry.key}_$mode');
        } finally {
          debugDefaultTargetPlatformOverride = null;
        }
      });
    }
    testWidgets('reason and feedback ($mode)', (tester) async {
      try {
        await pumpDevice(tester, brightness, const DeleteAccount());
        await capture(tester, 'reason_$mode');
        await tester.tap(find.text('Privacy concerns'));
        await tester.pump();
        await tester.tap(find.text('Continue'));
        await tester.pumpAndSettle();
        await capture(tester, 'feedback_$mode');
      } finally {
        debugDefaultTargetPlatformOverride = null;
      }
    });
    testWidgets('restore and finish confirmation ($mode)', (tester) async {
      try {
        await pumpDevice(
          tester,
          brightness,
          RestoreAccount(
            status: AccountDeletionStatus(
              pendingDeletion: true,
              wipeAt: DateTime.now().add(const Duration(days: 9, hours: 1)),
            ),
            onRestored: () {},
            onFinished: () {},
          ),
        );
        expect(find.text('You have 9 days left to restore your account.'), findsOneWidget);
        expect(find.textContaining('This ends the restore window.'), findsNothing);
        await capture(tester, 'restore_$mode');
        await tester.tap(find.byKey(const Key('finish_deleting')));
        await tester.pumpAndSettle();
        expect(find.textContaining('This ends the restore window.'), findsNothing);
        await tester.tap(find.byKey(const Key('finish_deleting_confirm')));
        await tester.pumpAndSettle();
        expect(find.textContaining('This ends the restore window.'), findsOneWidget);
        await capture(tester, 'finish_deleting_$mode');
      } finally {
        debugDefaultTargetPlatformOverride = null;
      }
    });

    testWidgets('B: pause-instead card for taking a break ($mode)', (tester) async {
      try {
        await pumpDevice(tester, brightness, const DeleteAccount());
        await tester.tap(find.text('Just taking a break'));
        await tester.pump();
        await tester.tap(find.text('Continue'));
        await tester.pumpAndSettle();
        expect(find.text('Pause Omi Instead?'), findsOneWidget);
        await capture(tester, 'b_pause_$mode');
        await tester.tap(find.text('Continue Deleting'));
        await tester.pumpAndSettle();
        expect(find.byType(TextField), findsOneWidget);
      } finally {
        debugDefaultTargetPlatformOverride = null;
      }
    });
  }
  testWidgets('Technical issues offers pause and local-only loss uses supplied restore window', (tester) async {
    try {
      await pumpDevice(
        tester,
        Brightness.light,
        DeleteAccount(
          loadPendingData: () async =>
              const DeletionPendingData(processingCount: 0, notUploadedCount: 1, gracePeriodDays: 7),
        ),
      );
      await tester.tap(find.text('Too many technical issues'));
      await tester.pump();
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();
      expect(find.text('Pause Omi Instead?'), findsOneWidget);
      await tester.tap(find.text('Continue Deleting'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Continue'));
      await tester.pumpAndSettle();
      expect(find.textContaining('still processing'), findsNothing);
      expect(find.textContaining("1 recording hasn't uploaded yet"), findsOneWidget);
      expect(find.textContaining('Sign in again within 7 days'), findsOneWidget);
      expect(tester.takeException(), isNull);
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  });
}
