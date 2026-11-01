import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';

// Only the settings-to-capture boundary is stubbed. Real capture retention is
// exercised separately by the CaptureReplayWorld tests.
class _Capture extends ChangeNotifier implements CaptureProvider {
  int changes = 0;
  @override
  bool get havingRecordingDevice => false;
  @override
  Future<void> onTranscriptionSettingsChanged() async => changes++;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Usage extends ChangeNotifier implements UsageProvider {
  @override
  bool get showSubscriptionUI => false;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late _Capture capture;
  late _Usage usage;

  setUp(() async {
    SharedPreferences.setMockInitialValues({
      'uid': 'fixture-user',
      'unlimitedLocalStorageEnabled': true,
      'permissionStoreRecordingsEnabled': true,
      'cachedConversations': <String>['retain-conversation-cache'],
    });
    await SharedPreferencesUtil.init();
    capture = _Capture();
    usage = _Usage();
  });
  tearDown(() {
    capture.dispose();
    usage.dispose();
  });

  Future<void> open(WidgetTester tester, CustomSttConfig config) async {
    await SharedPreferencesUtil().saveCustomSttConfig(config);
    await SharedPreferencesUtil().saveConfigForProvider(config.provider, config);
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<UsageProvider>.value(value: usage),
      ],
      child: MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
            builder: (context) => TextButton(
                  onPressed: () => Navigator.of(context)
                      .push(MaterialPageRoute<void>(builder: (_) => const TranscriptionSettingsPage())),
                  child: const Text('Open settings'),
                )),
      ),
    ));
    await tester.tap(find.text('Open settings'));
    await tester.pumpAndSettle();
    // The debug-only model performance snackbar otherwise covers Save.
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
  }

  Future<void> select(WidgetTester tester, TranscriptionMode mode) async {
    await tester.tap(find.byType(DropdownButton<TranscriptionMode>));
    await tester.pumpAndSettle();
    final dropdown = tester.widget<DropdownButton<TranscriptionMode>>(find.byType(DropdownButton<TranscriptionMode>));
    final item = dropdown.items!.singleWhere((item) => item.value == mode);
    await tester.tap(find.text((item.child as Text).data!).last);
    await tester.pumpAndSettle();
  }

  Future<void> save(WidgetTester tester) async {
    tester.testTextInput.hide();
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(find.text('Open settings'), findsOneWidget);
    expect(capture.changes, 1);
  }

  Future<void> expectDataPreserved() async {
    final prefs = await SharedPreferences.getInstance();
    expect(prefs.getString('uid'), 'fixture-user');
    expect(prefs.getBool('unlimitedLocalStorageEnabled'), isTrue);
    expect(prefs.getBool('permissionStoreRecordingsEnabled'), isTrue);
    expect(prefs.getStringList('cachedConversations'), ['retain-conversation-cache']);
  }

  testWidgets('edited Deepgram key reaches the effective saved request', (tester) async {
    await open(
        tester,
        const CustomSttConfig(
          provider: SttProvider.deepgramLive,
          apiKey: 'old-fixture-key',
          headers: {'Authorization': 'Token old-fixture-key', 'X-Custom': 'keep'},
          params: {'smart_format': 'true'},
        ));
    final keyField = find.byWidgetPredicate((w) => w is TextField && w.obscureText);
    await tester.enterText(keyField, 'new-fixture-key');
    await tester.ensureVisible(find.text('Advanced'));
    await tester.tap(find.text('Advanced'));
    await tester.pumpAndSettle();
    await save(tester);
    final saved = SharedPreferencesUtil().customSttConfig;
    expect(saved.apiKey, 'new-fixture-key');
    expect(saved.requestConfig['headers']['Authorization'], 'Token new-fixture-key');
    expect(saved.requestConfig['headers']['X-Custom'], 'keep');
    expect(saved.requestConfig['params']['smart_format'], 'true');
    await expectDataPreserved();
  });

  for (final mode in [TranscriptionMode.omi, TranscriptionMode.omiParakeet]) {
    testWidgets('cleared inactive Deepgram key cannot override $mode', (tester) async {
      await open(
          tester,
          const CustomSttConfig(
            provider: SttProvider.deepgramLive,
            apiKey: 'old-fixture-key',
            headers: {'Authorization': 'Token old-fixture-key'},
          ));
      await tester.enterText(find.byWidgetPredicate((w) => w is TextField && w.obscureText), '');
      await select(tester, mode);
      await save(tester);
      expect(SharedPreferencesUtil().customSttConfig.provider, SttProvider.omi);
      expect(SharedPreferencesUtil().transcriptionModel, mode == TranscriptionMode.omi ? 'soniox' : 'parakeet');
      final inactive = SharedPreferencesUtil().getConfigForProvider(SttProvider.deepgramLive)!;
      expect(inactive.apiKey, isNull);
      expect(inactive.requestConfig['headers']['Authorization'], 'Token ');
      await expectDataPreserved();
    });

    testWidgets('missing inactive Whisper model does not block saving $mode', (tester) async {
      await open(
          tester,
          const CustomSttConfig(
            provider: SttProvider.onDeviceWhisper,
            url: '/fixture/missing-model.bin',
          ));
      await select(tester, mode);
      await save(tester);
      expect(SharedPreferencesUtil().customSttConfig.provider, SttProvider.omi);
      expect(SharedPreferencesUtil().transcriptionModel, mode == TranscriptionMode.omi ? 'soniox' : 'parakeet');
      await expectDataPreserved();
    });
  }
}
