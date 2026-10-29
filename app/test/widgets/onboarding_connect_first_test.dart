import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/pages/onboarding/wrapper.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/experiments/onboarding_variant_gate.dart';
import 'package:omi/services/experiments/paywall_experiment.dart';
import 'package:omi/ui/ui.dart';

// The `connect_first` arm of `onboarding-variant`: Connect your Omi right after sign-up (no Back),
// then control's steps; an Omi paired there skips the phone voice intro. Readers the flag does not
// assign keep control's order.

typedef _Steps = OnboardingConnectFirstStepsForTest;

const _connectSteps = 'Press and hold your Omi until it vibrates. Then tap Connect.';
const _controlSubtitle = 'Pair your Omi and it captures your conversations hands-free, all day.';

/// Every step a reader walks from Connect until onboarding is done.
List<int> _walk({required bool pairedOmi, required bool setupPageEnabled}) {
  final order = <int>[];
  int? step = _Steps.connect;
  while (step != null) {
    order.add(step);
    step = _Steps.next(step, pairedOmi: pairedOmi, setupPageEnabled: setupPageEnabled);
  }
  return order;
}

class _QuietHome extends HomeProvider {
  @override
  Future setupHasSpeakerProfile() async {}
}

class _QuietAuth extends AuthenticationProvider {
  _QuietAuth() : super(initializeListeners: false);
}

final class _SignedIn implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(uid: 'u1', email: 'a@b.c', displayName: 'Alex');

  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;

  @override
  Future<void> signOut() async {}
}

Future<void> _saveOmi() => SharedPreferencesUtil().btDeviceSet(
      BtDevice(id: 'OMI-1', name: 'Omi', type: DeviceType.omi, rssi: -50),
    );

/// A signed-in reader on the Data & Privacy step whose flag read answers [variant].
Future<void> _pumpAtConsent(WidgetTester tester, String? variant) async {
  OnboardingVariantGate.warm(
    settledIdentity: () => 'u1',
    reload: () async => true,
    readVariant: (_) async => variant,
  );
  await tester.binding.setSurfaceSize(const Size(393, 852));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<HomeProvider>(create: (_) => _QuietHome()),
      ChangeNotifierProvider<AuthenticationProvider>(create: (_) => _QuietAuth()),
    ],
    child: MaterialApp(
      theme: buildOmiTheme(brightness: Brightness.light),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const OnboardingWrapper(),
    ),
  ));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 600));
  expect(find.byKey(const Key('ai_consent_agree')), findsOneWidget);
}

Future<void> _agree(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('ai_consent_agree')));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 600));
}

OnboardingProgressDots _dots(WidgetTester tester) =>
    tester.widget<OnboardingProgressDots>(find.byType(OnboardingProgressDots));

void main() {
  group('connect_first step order', () {
    test('Connect first, then control steps; the voice intro only without a paired Omi', () {
      expect(_walk(pairedOmi: false, setupPageEnabled: false), [
        _Steps.connect,
        _Steps.name,
        _Steps.language,
        _Steps.foundOmi,
        _Steps.permissions,
        _Steps.voiceIntro,
      ]);
      expect(_walk(pairedOmi: true, setupPageEnabled: false), [
        _Steps.connect,
        _Steps.name,
        _Steps.language,
        _Steps.foundOmi,
        _Steps.permissions,
      ]);
      // The flag-gated setup page still closes the flow, and Connect is never asked twice.
      expect(_walk(pairedOmi: false, setupPageEnabled: true).skip(5), [_Steps.voiceIntro, _Steps.setup]);
      expect(_walk(pairedOmi: true, setupPageEnabled: true).skip(4), [_Steps.permissions, _Steps.setup]);
      for (final paired in [false, true]) {
        for (final setup in [false, true]) {
          expect(_walk(pairedOmi: paired, setupPageEnabled: setup).where((s) => s == _Steps.connect), hasLength(1));
        }
      }
    });

    test('no Back on Connect or Name; Back elsewhere follows the walked order', () {
      for (final paired in [false, true]) {
        expect(_Steps.previous(_Steps.connect, pairedOmi: paired), isNull);
        expect(_Steps.previous(_Steps.name, pairedOmi: paired), isNull);
        expect(_Steps.previous(_Steps.language, pairedOmi: paired), _Steps.name);
        expect(_Steps.previous(_Steps.foundOmi, pairedOmi: paired), _Steps.language);
        expect(_Steps.previous(_Steps.permissions, pairedOmi: paired), _Steps.foundOmi);
      }
      expect(_Steps.previous(_Steps.voiceIntro, pairedOmi: false), _Steps.permissions);
      expect(_Steps.previous(_Steps.setup, pairedOmi: false), _Steps.voiceIntro);
      expect(_Steps.previous(_Steps.setup, pairedOmi: true), _Steps.permissions);
    });

    test('progress dots count control steps; a paired Omi drops the voice intro; Connect is not counted', () {
      expect(_Steps.progressSteps(pairedOmi: false), OnboardingProgressStepsForTest.steps);
      expect(
          _Steps.progressSteps(pairedOmi: true), [_Steps.name, _Steps.language, _Steps.foundOmi, _Steps.permissions]);
      expect(_Steps.progressSteps(pairedOmi: false), isNot(contains(_Steps.connect)));
    });

    test('a relaunch resumes the saved step, otherwise Connect', () {
      expect(_Steps.resume(_Steps.connect), _Steps.connect);
      expect(_Steps.resume(_Steps.language), _Steps.language);
      expect(_Steps.resume(_Steps.setup), _Steps.setup);
      for (final invalid in [-1, 0, 1, 10]) {
        expect(_Steps.resume(invalid), _Steps.connect, reason: 'saved $invalid');
      }
    });

    test('control order is unchanged for readers the flag does not assign', () {
      expect(OnboardingProgressStepsForTest.steps,
          [_Steps.name, _Steps.language, _Steps.foundOmi, _Steps.permissions, _Steps.voiceIntro]);
      expect(OnboardingWrapper.resumeStepForTesting(-1), _Steps.name);
      expect(OnboardingWrapper.resumeStepForTesting(_Steps.connect), _Steps.connect);
      expect(
          OnboardingWrapper.previousStepForTesting(
              currentIndex: _Steps.connect, setupPageEnabled: false, knowledgeGraphStepEnabled: false),
          _Steps.voiceIntro);
      expect(
          OnboardingWrapper.previousStepForTesting(
              currentIndex: _Steps.name, setupPageEnabled: false, knowledgeGraphStepEnabled: false),
          isNull);
    });
  });

  group('Connect step copy', () {
    Widget host(Widget child) => MaterialApp(
          theme: buildOmiTheme(brightness: Brightness.light),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: child),
        );

    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    testWidgets('connect_first says what to press; control keeps its subtitle', (tester) async {
      await tester.pumpWidget(host(OnboardingCompleteScreen(
          description: _connectSteps, onComplete: () {}, emit: (_) {}, setProperty: (_, __) {})));
      expect(find.text(_connectSteps), findsOneWidget);
      expect(find.text(_controlSubtitle), findsNothing);

      await tester.pumpWidget(host(OnboardingCompleteScreen(onComplete: () {}, emit: (_) {}, setProperty: (_, __) {})));
      expect(find.text(_controlSubtitle), findsOneWidget);
      expect(find.text(_connectSteps), findsNothing);
    });
  });

  group('wrapper', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
      SharedPreferencesUtil().uid = 'u1';
      AuthService.installLocalHarnessTokenGateway(_SignedIn());
      OnboardingVariantGate.resetForTesting();
      PaywallExperiment.resetForTesting();
    });

    testWidgets('connect_first: Connect right after consent, no Back; Skip moves on to Name', (tester) async {
      await _pumpAtConsent(tester, 'connect_first');
      await _agree(tester);

      expect(find.byKey(const Key('first_capture_omi')), findsOneWidget);
      expect(find.text(_connectSteps), findsOneWidget);
      expect(find.byKey(const Key('onboarding_back')), findsNothing);
      expect(find.byType(OnboardingProgressDots), findsNothing);

      await tester.tap(find.byKey(const Key('onboarding_complete_start')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(find.byKey(const Key('onboarding_name_continue')), findsOneWidget);
      expect(find.byKey(const Key('onboarding_back')), findsNothing, reason: 'Name never leads back to Connect');
      expect(_dots(tester).current, 0);
      expect(_dots(tester).total, 5, reason: 'no Omi paired: the voice intro is still ahead');
      expect(SharedPreferencesUtil().getInt('onboarding/connectFirst/resumeStep/u1', defaultValue: -1), _Steps.name);
      expect(SharedPreferencesUtil().getInt('onboarding/resumeStep/u1', defaultValue: -1), -1);
    });

    testWidgets('connect_first: an Omi paired at Connect takes the voice intro out of the steps', (tester) async {
      await _pumpAtConsent(tester, 'connect_first');
      await _agree(tester);
      // What a pairing leaves behind: the Omi saved for this account.
      await _saveOmi();
      expect(jsonDecode(SharedPreferencesUtil().getStringList('btDevices').single)['id'], 'OMI-1');

      await tester.tap(find.byKey(const Key('onboarding_complete_start')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));

      expect(find.byKey(const Key('onboarding_name_continue')), findsOneWidget);
      expect(_dots(tester).total, 4);
    });

    testWidgets('control (and an unread flag): Name first, no Connect step up front', (tester) async {
      for (final variant in ['control', null]) {
        await _pumpAtConsent(tester, variant);
        await _agree(tester);

        expect(find.byKey(const Key('onboarding_name_continue')), findsOneWidget, reason: 'variant $variant');
        expect(find.byKey(const Key('first_capture_omi')), findsNothing);
        expect(find.byKey(const Key('onboarding_back')), findsNothing);
        expect(_dots(tester).total, 5);
        expect(SharedPreferencesUtil().getInt('onboarding/connectFirst/resumeStep/u1', defaultValue: -1), -1);

        await tester.pumpWidget(const SizedBox());
        SharedPreferencesUtil().aiConsentGiven = false;
        OnboardingVariantGate.resetForTesting();
      }
    });
  });
}
