import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/sockets/local_stt_failure.dart';
import 'package:omi/ui/components/local_stt_recovery_notice.dart';

void main() {
  testWidgets('permission action probes explicit configured language through actual channel', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SharedPreferencesUtil().userPrimaryLanguage = 'zz';
    await SharedPreferencesUtil()
        .saveCustomSttConfig(const CustomSttConfig(provider: SttProvider.onDeviceWhisper, language: 'en'));
    final languages = <String>[];
    const channel = MethodChannel('com.omi.ios/speech');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'prepareSpeech');
      languages.add(call.arguments['language'] as String);
      return {'engine': 'sfspeech', 'status': 'ready'};
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    var retries = 0;
    await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
            body: LocalSttRecoveryNotice(
                failure: const LocalSttFailure('permission_required'),
                onRetry: () async {
                  retries++;
                },
                onSetup: () {}))));
    await tester.tap(find.byKey(const ValueKey('local_stt_setup')));
    await tester.pumpAndSettle();
    expect(languages, ['en']);
    expect(retries, 1);
  });
  for (final status in ['permission_denied', 'permission_required', 'unavailable']) {
    testWidgets('$status explains custody and exposes working recovery actions at 200% text', (tester) async {
      var settings = 0;
      var setup = 0;
      var retries = 0;
      var requests = 0;
      tester.view.physicalSize = const Size(640, 1000);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          builder: (context, child) =>
              MediaQuery(data: MediaQuery.of(context).copyWith(textScaler: const TextScaler.linear(2)), child: child!),
          home: Scaffold(
              body: SingleChildScrollView(
                  child: LocalSttRecoveryNotice(
            failure: LocalSttFailure(status, canProbeRecovery: true),
            onRetry: () async {
              retries++;
            },
            onSetup: () {
              setup++;
            },
            openSettings: () async {
              settings++;
              return true;
            },
            preparePermission: () async {
              requests++;
              return true;
            },
          )))));
      expect(find.text('Transcription is unavailable — recording continues and your audio is saved.'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('local_stt_setup')));
      await tester.pumpAndSettle();
      expect(settings, status == 'permission_denied' ? 1 : 0);
      expect(requests, status == 'permission_required' ? 1 : 0);
      expect(setup, status == 'unavailable' ? 1 : 0);
      await tester.tap(find.byKey(const ValueKey('local_stt_retry')));
      await tester.pumpAndSettle();
      expect(retries, status == 'permission_required' ? 2 : 1);
      expect(tester.takeException(), isNull);
    });
  }
}
