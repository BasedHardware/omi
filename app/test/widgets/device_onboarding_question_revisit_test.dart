import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/interactive_device_onboarding/steps/single_press_step.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/ui.dart';

/// Chat as the pendant question path fills it; no network.
class _Messages extends ChangeNotifier implements MessageProvider {
  @override
  List<ServerMessage> messages = [];

  void add(String id, String text, MessageSender sender) {
    messages = [
      ...messages,
      ServerMessage(id, DateTime.now(), text, sender, MessageType.text, null, false, [], [], [])
    ];
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _step(DeviceOnboardingProvider provider, _Messages chat) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<DeviceOnboardingProvider>.value(value: provider),
      ChangeNotifierProvider<MessageProvider>.value(value: chat),
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
      home: Scaffold(
        body: Consumer<DeviceOnboardingProvider>(
          builder: (context, p, _) => p.currentStep == DeviceOnboardingProvider.askQuestionStep
              ? SinglePressStep(onComplete: () {})
              : const SizedBox.shrink(),
        ),
      ),
    ),
  );
}

/// Starts the tutorial and answers the question step the way the pendant path does: two presses,
/// then the question and Omi's answer arrive in chat.
Future<(DeviceOnboardingProvider, _Messages)> _answered(WidgetTester tester) async {
  final provider = DeviceOnboardingProvider()
    ..startOnboarding()
    ..advanceStep();
  final chat = _Messages();
  await tester.pumpWidget(_step(provider, chat));
  provider
    ..onButtonEvent(1)
    ..onButtonEvent(1);
  await tester.pump();
  chat
    ..add('q1', 'What is on my calendar today?', MessageSender.human)
    ..add('a1', 'A design review at 2 pm.', MessageSender.ai);
  await tester.pump(const Duration(milliseconds: 300));
  expect(find.text('A design review at 2 pm.'), findsOneWidget);
  return (provider, chat);
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('reopening the question step from All Set shows the earlier answer (#20787)', (tester) async {
    final (provider, _) = await _answered(tester);
    while (provider.currentStep < DeviceOnboardingProvider.allSetStep) {
      provider.advanceStep();
    }
    await tester.pump();

    provider.goToStep(DeviceOnboardingProvider.askQuestionStep);
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('A design review at 2 pm.'), findsOneWidget);
    expect(find.textContaining('Processing'), findsNothing);
    expect(find.text('Continue'), findsOneWidget);
  });

  test('a step reopened from All Set returns to All Set when finished (#20787)', () {
    final provider = DeviceOnboardingProvider()..startOnboarding();
    while (provider.currentStep < DeviceOnboardingProvider.allSetStep) {
      provider.advanceStep();
    }

    provider.goToStep(DeviceOnboardingProvider.powerCycleStep);
    expect(provider.reviewingFromSummary, isTrue);

    provider.returnToSummary();
    expect(provider.currentStep, DeviceOnboardingProvider.allSetStep);
    expect(provider.reviewingFromSummary, isFalse);
  });

  test('walking forward through the tutorial is not a summary review', () {
    final provider = DeviceOnboardingProvider()..startOnboarding();
    provider.advanceStep();
    expect(provider.reviewingFromSummary, isFalse);

    provider.goToStep(DeviceOnboardingProvider.doublePressStep);
    expect(provider.reviewingFromSummary, isFalse);

    // Restarting the tutorial clears a review in progress.
    while (provider.currentStep < DeviceOnboardingProvider.allSetStep) {
      provider.advanceStep();
    }
    provider
      ..goToStep(DeviceOnboardingProvider.voiceReplyStep)
      ..startOnboarding();
    expect(provider.reviewingFromSummary, isFalse);
  });
}
