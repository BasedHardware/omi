import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/experiments/onboarding_webview_gate.dart';

// Web onboarding is fail-closed: off, slow, erroring, or a payload without an https URL all mean
// the native onboarding exactly as before.

void main() {
  setUp(OnboardingWebviewGate.resetForTesting);

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
      settledIdentity: () => 'u',
      reload: () async {},
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
      settledIdentity: () => 'u',
      reload: () async {},
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
    expect(
        await OnboardingWebviewGate.resolve(
            settledIdentity: () => 'u', reload: () async {}, readFlag: (_) => Future.error(StateError('no sdk'))),
        isNull);
  });

  test('waits for the identity to settle and reloads flags before the first read', () async {
    final order = <String>[];
    var polls = 0;
    final url = await OnboardingWebviewGate.resolve(
      settledIdentity: () => ++polls < 4 ? null : 'u',
      reload: () async => order.add('reload'),
      readFlag: (_) async {
        order.add('read');
        return true;
      },
      readPayload: (_) async => {'url': 'https://x.example/onboarding'},
    );
    expect(url, Uri.parse('https://x.example/onboarding'));
    expect(order, ['reload', 'read']);
    expect(polls, greaterThanOrEqualTo(4));
  });

  test('no identity within the wait -> native, without reading anything', () async {
    var reads = 0;
    final url = await OnboardingWebviewGate.resolve(
      settledIdentity: () => null,
      identityWait: const Duration(milliseconds: 200),
      reload: () async => reads++,
      readFlag: (_) async {
        reads++;
        return true;
      },
    );
    expect(url, isNull);
    expect(reads, 0);
  });

  test('a warm-up started on the consent screen answers the tap without restarting the wait', () async {
    var polls = 0;
    var reads = 0;
    OnboardingWebviewGate.warm(
      settledIdentity: () => ++polls < 6 ? null : 'u',
      reload: () async {},
      readFlag: (_) async {
        reads++;
        return true;
      },
      readPayload: (_) async => {'url': 'https://x.example/onboarding'},
    );
    final url = await OnboardingWebviewGate.resolve(settledIdentity: () => null, identityWait: Duration.zero);
    expect(url, Uri.parse('https://x.example/onboarding'));
    expect(reads, 1);
    // The warm-up is consumed: the next resolve is a cold read again.
    expect(await OnboardingWebviewGate.resolve(settledIdentity: () => null, identityWait: Duration.zero), isNull);
  });
}
