import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/profile.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';

class _FakePathProviderPlatform extends PathProviderPlatform {
  final Directory docsDir;
  _FakePathProviderPlatform(this.docsDir);

  @override
  Future<String?> getApplicationDocumentsPath() async => docsDir.path;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempRoot;
  late Directory defaultDocsDir;

  setUp(() async {
    tempRoot = await Directory.systemTemp.createTemp('profile_audio_test');
    defaultDocsDir = Directory('${tempRoot.path}/docs')..createSync(recursive: true);
    PathProviderPlatform.instance = _FakePathProviderPlatform(defaultDocsDir);

    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  tearDown(() async {
    if (tempRoot.existsSync()) {
      await tempRoot.delete(recursive: true);
    }
  });

  testWidgets('Audio Storage Folder section renders and allows resetting to default', (tester) async {
    SharedPreferencesUtil().customAudioStorageDir = '/storage/emulated/0/Music/Omi';
    await SharedPreferencesUtil().saveString('batchAudioDir', '/storage/emulated/0/Music/Omi');

    final captureProvider = CaptureProvider();
    addTearDown(captureProvider.dispose);

    final recordingsProvider = LocalRecordingsProvider();
    addTearDown(recordingsProvider.dispose);

    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<CaptureProvider>.value(value: captureProvider),
          ChangeNotifierProvider<LocalRecordingsProvider>.value(value: recordingsProvider),
        ],
        child: const MaterialApp(
          localizationsDelegates: [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: ProfilePage(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Find and tap Transcribe Later tile
    final transcribeLaterTile = find.text('Transcribe Later');
    expect(transcribeLaterTile, findsOneWidget);
    await tester.tap(transcribeLaterTile);
    await tester.pumpAndSettle();

    // Audio storage section must be visible in the bottom sheet
    expect(find.text('Audio Storage Folder'), findsOneWidget);
    expect(find.text('/storage/emulated/0/Music/Omi'), findsOneWidget);
    expect(find.text('Change Folder'), findsOneWidget);
    expect(find.text('Reset'), findsOneWidget);

    // Tap Reset button
    await tester.tap(find.text('Reset'));
    await tester.pumpAndSettle();

    // Should now show default storage description and hide Reset button
    expect(SharedPreferencesUtil().customAudioStorageDir, isEmpty);
    expect(find.textContaining('Default App Storage'), findsOneWidget);
    expect(find.text('Reset'), findsNothing);
  });
}
