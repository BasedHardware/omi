import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/integrations/integration_oauth.dart';
import '../../support/test_browser.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late TestBrowser browser;
  setUp(() {
    browser = TestBrowser();
    browser.install();
  });
  tearDown(() => browser.dispose());

  test('uses the actual external-browser result despite a false package query', () async {
    expect(await launchIntegrationOAuth(() async => 'https://example.test/oauth?state=opaque'), isTrue);
    expect(browser.queries, 0);
    expect(browser.launches.single, ('https://example.test/oauth?state=opaque', false, false));
    browser.opened = false;
    expect(await launchIntegrationOAuth(() async => 'https://example.test/oauth'), isFalse);
  });

  test('failed or malformed authorization URL never launches a browser', () async {
    for (final url in [null, '', 'not a url', 'javascript:alert(1)', 'https://user:password@example.test/']) {
      expect(await launchIntegrationOAuth(() async => url), isFalse);
    }
    expect(await launchIntegrationOAuth(() async => throw StateError('private provider details')), isFalse);
    expect(browser.launches, isEmpty);
  });

  testWidgets('expired URL lookup cannot launch late and a hung launcher releases its caller', (tester) async {
    final url = Completer<String?>();
    bool? result;
    unawaited(
        launchIntegrationOAuth(() => url.future, deadline: const Duration(seconds: 1)).then((value) => result = value));
    await tester.pump(const Duration(seconds: 2));
    expect(result, isFalse);
    url.complete('https://example.test/oauth');
    await tester.pump();
    expect(browser.launches, isEmpty);

    final launched = Completer<bool>();
    result = null;
    unawaited(launchIntegrationOAuth(() async => 'https://example.test/oauth',
            openBrowser: (_) => launched.future, deadline: const Duration(seconds: 1))
        .then((value) => result = value));
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));
    expect(result, isFalse);
    launched.complete(true);
    await tester.pump();
    expect(result, isFalse);
  });
  testWidgets('leaving an authorization owner prevents a late URL from launching', (tester) async {
    var current = true;
    final pending = Completer<String?>();
    final result = launchIntegrationOAuth(() => pending.future, isCurrent: () => current);
    current = false;
    pending.complete('https://vendor.test/oauth');
    await tester.pump();
    expect(await result, isFalse);
    expect(browser.launches, isEmpty);
  });

  test('a late browser receipt cannot start completion for a departed owner', () async {
    var current = true;
    final opened = Completer<bool>();
    final launching = Completer<void>();
    final result = launchIntegrationOAuth(() async => 'https://vendor.test/oauth',
        openBrowser: (_) {
          launching.complete();
          return opened.future;
        },
        isCurrent: () => current);
    await launching.future;
    current = false;
    opened.complete(true);
    expect(await result, isFalse);
  });
}
