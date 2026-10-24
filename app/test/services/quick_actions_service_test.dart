import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/quick_actions_service.dart';
import 'package:omi/ui/ui.dart';

class _MockCapture extends ChangeNotifier implements CaptureProvider {
  int pauseCalls = 0;
  int resumeCalls = 0;
  Object? pauseError;
  Object? resumeError;

  @override
  Future<void> pauseCapture() async {
    pauseCalls++;
    final error = pauseError;
    if (error != null) throw error;
  }

  @override
  Future<void> resumeCapture() async {
    resumeCalls++;
    final error = resumeError;
    if (error != null) throw error;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  Future<void> pump(
    WidgetTester tester, {
    required _MockCapture capture,
    required Widget child,
  }) async {
    await tester.pumpWidget(
      ChangeNotifierProvider<CaptureProvider>.value(
        value: capture,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          theme: buildOmiTheme(),
          home: Scaffold(body: Center(child: child)),
        ),
      ),
    );
    await tester.pump();
  }

  group('QuickActionsService mute/unmute error handling', () {
    testWidgets('successful pause and resume invoke captureProvider methods', (tester) async {
      final capture = _MockCapture();

      await pump(
        tester,
        capture: capture,
        child: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              await QuickActionsService.instance.toggleMuteForTesting(context, mute: true);
              await QuickActionsService.instance.toggleMuteForTesting(context, mute: false);
            },
            child: const Text('trigger'),
          ),
        ),
      );

      await tester.tap(find.text('trigger'));
      await tester.pump();

      expect(capture.pauseCalls, 1);
      expect(capture.resumeCalls, 1);
      expect(find.text(en.somethingWentWrong), findsNothing);
    });

    testWidgets('failing pauseCapture catches error and displays somethingWentWrong feedback', (tester) async {
      final capture = _MockCapture()..pauseError = StateError('pause failed');

      await pump(
        tester,
        capture: capture,
        child: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () => QuickActionsService.instance.toggleMuteForTesting(context, mute: true),
            child: const Text('mute'),
          ),
        ),
      );

      await tester.tap(find.text('mute'));
      await tester.pump();

      expect(capture.pauseCalls, 1);
      expect(find.text(en.somethingWentWrong), findsOneWidget);
    });

    testWidgets('failing resumeCapture catches error and displays somethingWentWrong feedback', (tester) async {
      final capture = _MockCapture()..resumeError = StateError('resume failed');

      await pump(
        tester,
        capture: capture,
        child: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () => QuickActionsService.instance.toggleMuteForTesting(context, mute: false),
            child: const Text('unmute'),
          ),
        ),
      );

      await tester.tap(find.text('unmute'));
      await tester.pump();

      expect(capture.resumeCalls, 1);
      expect(find.text(en.somethingWentWrong), findsOneWidget);
    });
  });
}
