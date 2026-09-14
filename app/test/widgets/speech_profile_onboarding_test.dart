import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/speech_profile_widget.dart';
import 'package:omi/pages/speech_profile/speech_topics_card.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/speech_profile_provider.dart';

// Only the hardware/bootstrap boundary is faked; render the real enrollment
// widget and deliver provider errors through its production MessageListener.
class _SpeechProvider extends SpeechProfileProvider {
  _SpeechProvider({bool recording = true}) {
    startedRecording = recording;
    isInitialising = !recording;
  }

  @override
  Future<void> close() async {}
}

class _CaptureProvider extends ChangeNotifier implements CaptureProvider {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _HomeProvider extends ChangeNotifier implements HomeProvider {
  @override
  bool get hasSetPrimaryLanguage => true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _pump(WidgetTester tester, _SpeechProvider speech, VoidCallback skip) async {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<SpeechProfileProvider>.value(value: speech),
      ChangeNotifierProvider<CaptureProvider>(create: (_) => _CaptureProvider()),
      ChangeNotifierProvider<HomeProvider>(create: (_) => _HomeProvider()),
    ],
    child: MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: SpeechProfileWidget(goNext: () {}, onSkip: skip)),
    ),
  ));
  await tester.pump();
}

void main() {
  testWidgets('explains why and duration, accepts any topic, and keeps Skip secondary', (tester) async {
    var skipped = false;
    final speech = _SpeechProvider();
    await _pump(tester, speech, () => skipped = true);
    expect(find.text('Teach Omi your voice'), findsOneWidget);
    expect(find.text('So Omi knows which voice is yours — talk for about 5 seconds about anything.'), findsOneWidget);
    expect(find.byType(SpeechTopicsCard), findsNothing);
    final skip = find.widgetWithText(TextButton, 'Skip for now');
    expect(skip, findsOneWidget);
    await tester.tap(skip);
    expect(skipped, isTrue);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('intro explains the same sample and keeps Skip available during startup', (tester) async {
    var skipped = false;
    final speech = _SpeechProvider(recording: false);
    await _pump(tester, speech, () => skipped = true);
    expect(find.text('So Omi knows which voice is yours — talk for about 5 seconds about anything.'), findsOneWidget);
    final skip = find.widgetWithText(TextButton, 'Skip for now');
    expect(skip, findsOneWidget);
    await tester.tap(skip);
    expect(skipped, isTrue);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('upload failure offers Skip and never displays All Done', (tester) async {
    var skipped = false;
    final speech = _SpeechProvider();
    await _pump(tester, speech, () => skipped = true);
    speech.notifyError('UPLOAD_FAILED');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    final context = tester.element(find.byType(SpeechProfileWidget));
    expect(find.text(AppLocalizations.of(context).allDone), findsNothing);
    final skip = find.descendant(of: find.byType(AlertDialog), matching: find.text('Skip for now'));
    expect(skip, findsOneWidget);
    await tester.tap(skip);
    await tester.pump();
    expect(skipped, isTrue);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
