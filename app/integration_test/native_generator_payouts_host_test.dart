import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/pages/payments/payments_page.dart';
import 'package:omi/pages/payments/stripe_connect_setup.dart';
import 'package:omi/pages/settings/ai_app_generator_page.dart';
import 'package:omi/pages/settings/ai_app_generator_provider.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

/// A real 1×1 PNG for the generated icon.
final _icon =
    base64Decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=');

/// The generator owner with generate, icon and submit replaced by inert fakes.
class _FakeGenerator extends AiAppGeneratorProvider {
  GenerationState fakeState = GenerationState.idle;
  String? name, description;
  Uint8List? icon;
  final prompts = <String>[];
  int submits = 0, regenerates = 0;

  @override
  GenerationState get state => fakeState;
  @override
  GenerationStep get currentStep => GenerationStep.finalTouches;
  @override
  int get currentStepIndex => GenerationStep.finalTouches.index;
  @override
  String? get errorMessage => null;
  @override
  String? get generatedName => name;
  @override
  String? get generatedDescription => description;
  @override
  String? get generatedCategory => name == null ? null : 'productivity-and-organization';
  @override
  List<String>? get generatedCapabilities => name == null ? null : const ['chat', 'memories'];
  @override
  Uint8List? get generatedIconBytes => icon;
  @override
  List<String> get samplePrompts => const ['A focus coach for deep work', 'A gratitude journal'];
  @override
  bool get isLoadingPrompts => false;
  @override
  bool get isLoading => fakeState != GenerationState.idle;
  @override
  bool get isGenerating => fakeState == GenerationState.generatingApp || fakeState == GenerationState.generatingIcon;
  @override
  bool get hasGeneratedApp => name != null && description != null && icon != null && !isGenerating;

  @override
  Future<void> fetchSamplePrompts() async {}

  @override
  Future<bool> generateApp(String prompt) async {
    prompts.add(prompt);
    name = 'Focus Coach';
    description = 'Keeps your deep-work sessions on track.';
    icon = _icon;
    notifyListeners();
    return true;
  }

  @override
  Future<bool> regenerateIcon() async {
    regenerates++;
    icon = Uint8List.fromList(_icon);
    notifyListeners();
    return true;
  }

  @override
  Future<String?> submitGeneratedApp() async {
    submits++;
    return null;
  }
}

/// The payout owner with payment status and countries replaced by fixtures.
class _FakePayments extends PaymentMethodProvider {
  _FakePayments({this.connected = false});
  final bool connected;
  int statusLoads = 0;

  @override
  bool get isStripeConnected => connected;
  @override
  PaymentConnectionState get stripeConnectionState =>
      connected ? PaymentConnectionState.connected : PaymentConnectionState.notConnected;
  @override
  bool get isStripePolling => false;
  @override
  bool get isLoading => false;
  @override
  PaymentMethodType? get activeMethod => null;
  @override
  List<Map<String, dynamic>> get supportedCountries => const [
        {'id': 'US', 'name': 'United States'},
        {'id': 'DE', 'name': 'Germany'},
        {'id': 'IN', 'name': 'India'},
      ];
  @override
  Future getSupportedCountries() async {}
  @override
  Future getPaymentMethodsStatus() async => statusLoads++;
  @override
  void stopStripePolling() {}
}

void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('native AI app generator keeps generate, icon and create with the existing owner', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final generator = _FakeGenerator();
      await tester.pumpWidget(nativeHostApp(AiAppGeneratorPage(createProvider: () => generator)));
      await checkNativeHost(tester, 'native-app-generator-payouts-generator-prompt-dark');

      await nativeProjectedRow(tester, 'ai_gen_prompt:0').action!(null);
      await tester.pump();
      expect(nativeProjectedRow(tester, 'ai_gen_prompt_text').value, 'A focus coach for deep work');
      generator
        ..fakeState = GenerationState.generatingIcon
        ..notifyListeners();
      await tester.pump();
      expect(nativeProjectedRow(tester, 'ai_gen_progress').value, 5.0);
      await checkNativeHost(tester, 'native-app-generator-payouts-generator-generating-dark');
      generator
        ..fakeState = GenerationState.idle
        ..notifyListeners();
      await tester.pump();
      await nativeProjectedRow(tester, 'ai_gen_send').action!(null);
      await tester.pump();
      expect(generator.prompts, ['A focus coach for deep work']);

      // The icon crosses as a temporary PNG once the real file write completes.
      for (var attempt = 0; attempt < 50 && nativeProjectedRow(tester, 'ai_gen_preview').imageUri == null; attempt++) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
        await tester.pump();
      }
      expect(nativeProjectedRow(tester, 'ai_gen_preview').imageUri, startsWith('file:///'));
      await checkNativeHost(tester, 'native-app-generator-payouts-generator-generated-dark');

      await nativeProjectedRow(tester, 'ai_gen_create').action!(null);
      await tester.pump();
      expect(generator.submits, 1);
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('native payouts and Stripe setup keep the payment owner', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final payments = _FakePayments(connected: true);
      await tester.pumpWidget(nativeHostApp(const PaymentsPage(),
          providers: [ChangeNotifierProvider<PaymentMethodProvider>.value(value: payments)]));
      await checkNativeHost(tester, 'native-app-generator-payouts-payouts-dark');
      expect(nativeProjectedRow(tester, 'payout_method:stripe').options.keys, ['update', 'set_active']);
      expect(payments.statusLoads, greaterThanOrEqualTo(1));

      await tester.pumpWidget(const SizedBox());
      final setup = _FakePayments();
      await tester.pumpWidget(nativeHostApp(const StripeConnectSetup(),
          providers: [ChangeNotifierProvider<PaymentMethodProvider>.value(value: setup)]));
      await checkNativeHost(tester, 'native-app-generator-payouts-stripe-setup-dark');
      expect(nativeProjectedRow(tester, 'stripe_connect').projection['enabled'], isFalse);
      await nativeProjectedRow(tester, 'stripe_country').action!('US');
      await tester.pump();
      expect(setup.selectedCountryId, 'US');
      expect(nativeProjectedRow(tester, 'stripe_connect').projection['enabled'], isTrue);
      await checkNativeHost(tester, 'native-app-generator-payouts-stripe-setup-selected-dark');
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  });
}
