import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/sockets/local_stt_failure.dart';
import 'package:omi/ui/components/local_stt_recovery_notice.dart';

void main() {
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
