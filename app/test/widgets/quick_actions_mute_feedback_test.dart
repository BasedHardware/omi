import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/quick_actions_service.dart';

/// Pause and resume fail the way coordinator dispatches do when their effect fails.
class _FailingCapture extends ChangeNotifier implements CaptureProvider {
  var pauses = 0;
  var resumes = 0;

  @override
  Future<void> pauseCapture() async {
    pauses++;
    throw StateError('pause effect failed');
  }

  @override
  Future<void> resumeCapture() async {
    resumes++;
    throw StateError('resume effect failed');
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<_FailingCapture> _pump(WidgetTester tester) async {
  final capture = _FailingCapture();
  addTearDown(capture.dispose);
  await tester.pumpWidget(
    ChangeNotifierProvider<CaptureProvider>.value(
      value: capture,
      child: MaterialApp(
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const Scaffold(body: SizedBox.expand()),
      ),
    ),
  );
  return capture;
}

void main() {
  // #19245: the Home Screen quick actions left a failed pause/resume as an unhandled future.
  testWidgets('a failed Mute from the quick action says so instead of failing silently', (tester) async {
    final capture = await _pump(tester);

    QuickActionsService.instance.debugHandleShortcut('mute');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    expect(capture.pauses, 1);
    expect(find.text(l10n.somethingWentWrong), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a failed Unmute from the quick action says so instead of failing silently', (tester) async {
    final capture = await _pump(tester);

    QuickActionsService.instance.debugHandleShortcut('unmute');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
    expect(capture.resumes, 1);
    expect(find.text(l10n.somethingWentWrong), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
