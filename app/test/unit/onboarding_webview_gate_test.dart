import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/experiments/onboarding_webview_gate.dart';

// Web onboarding is fail-closed: off, slow, erroring, or a payload without an https URL all mean
// the native onboarding exactly as before.

void main() {
  test('flag key is the registered PostHog key', () {
    expect(OnboardingWebviewGate.enabledFlag, 'onboarding-webview');
    expect(OnboardingWebviewGate.debugOverrideActive, isFalse);
  });

  test('parse accepts only an https URL from a map or a JSON string', () {
    expect(
        OnboardingWebviewGate.parse(enabled: true, payload: {'url': 'https://omi-paywall.vercel.app/onboarding.html'}),
        Uri.parse('https://omi-paywall.vercel.app/onboarding.html'));
    expect(OnboardingWebviewGate.parse(enabled: true, payload: '{"url":"https://x.example/o"}'),
        Uri.parse('https://x.example/o'));
    expect(OnboardingWebviewGate.parse(enabled: true, payload: {'url': 'http://x.example'}), isNull);
    expect(OnboardingWebviewGate.parse(enabled: true, payload: {}), isNull);
    expect(OnboardingWebviewGate.parse(enabled: true, payload: 'garbage'), isNull);
    expect(OnboardingWebviewGate.parse(enabled: false, payload: {'url': 'https://x.example'}), isNull);
  });

  test('flag off -> native, without reading the payload', () async {
    var payloadReads = 0;
    final url = await OnboardingWebviewGate.resolve(
      readFlag: (_) async => false,
      readPayload: (_) async {
        payloadReads++;
        return {'url': 'https://x.example'};
      },
    );
    expect(url, isNull);
    expect(payloadReads, 0);
  });

  test('flag on -> the payload URL', () async {
    final keys = <String>[];
    final url = await OnboardingWebviewGate.resolve(
      readFlag: (key) async {
        keys.add(key);
        return true;
      },
      readPayload: (_) async => {'url': 'https://x.example/onboarding'},
    );
    expect(url, Uri.parse('https://x.example/onboarding'));
    expect(keys, ['onboarding-webview']);
  });

  test('flag read error -> native (fail closed)', () async {
    expect(await OnboardingWebviewGate.resolve(readFlag: (_) => Future.error(StateError('no sdk'))), isNull);
  });
}
