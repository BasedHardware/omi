import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/services/on_device/on_device_transcription_controller.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/widgets/freemium_switch_dialog.dart';
import '../support/on_device_fakes.dart';

class _Capture extends ChangeNotifier implements CaptureProvider {
  @override
  bool get freemiumThresholdReached => true;
  @override
  bool get freemiumRequiresUserAction => true;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  final original = OnDeviceTranscriptionController.instance;
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    FreemiumTranscriptionService().reset();
    FreemiumTranscriptionService().resetDialogShownFlag();
  });
  tearDown(() => OnDeviceTranscriptionController.instance = original);
  for (final active in [false, true]) {
    testWidgets('free monthly cap queues the choice only with gate active=$active', (tester) async {
      final controller = OnDeviceTranscriptionController(model: FakeOnDeviceModel());
      if (active) controller.debugActivate();
      OnDeviceTranscriptionController.instance = controller;
      final usage = UsageProvider()
        ..debugSetSubscription(UserSubscriptionResponse(
            subscription: Subscription(plan: PlanType.basic, status: SubscriptionStatus.active),
            transcriptionSecondsUsed: 3600,
            transcriptionSecondsLimit: 3600,
            wordsTranscribedUsed: 0,
            wordsTranscribedLimit: 0,
            insightsGainedUsed: 0,
            insightsGainedLimit: 0));
      late BuildContext context;
      await tester.pumpWidget(ChangeNotifierProvider.value(
          value: usage,
          child: MaterialApp(home: Builder(builder: (value) {
            context = value;
            return const SizedBox();
          }))));
      final queue = PromptQueue(contextProvider: () => context)..blocked = () => true;
      final handler = FreemiumSwitchHandler(queue: queue);
      final capture = _Capture();
      expect(handler.checkAndShowPaywall(context, capture), active);
      expect(handler.checkAndShowPaywall(context, capture), isFalse); // Once per crossing/session.
      handler.dispose();
      capture.dispose();
      controller.dispose();
    });
  }
}
