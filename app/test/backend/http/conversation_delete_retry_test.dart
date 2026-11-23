import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/api/conversations.dart';

/// A busy account gate answers DELETE with 409 `account_gate_busy` + Retry-After; the delete waits
/// and retries within its budget instead of failing (a bulk delete used to lose most of its rows).
void main() {
  late DateTime clock;
  late int attempts;
  late List<Duration> waits;

  setUp(() {
    clock = DateTime.utc(2026, 11, 13);
    attempts = 0;
    waits = [];
  });

  Future<bool> delete(http.Response? Function(int attempt) answer) => deleteConversationServer(
        'c1',
        send: () async => answer(++attempts),
        wait: (delay) async {
          waits.add(delay);
          clock = clock.add(delay);
        },
        now: () => clock,
      );

  http.Response busy([String? retryAfter]) => http.Response(
        '{"detail":"account_gate_busy"}',
        409,
        headers: {if (retryAfter != null) 'retry-after': retryAfter},
      );

  test('409 then 204 retries once after Retry-After and succeeds', () async {
    expect(await delete((attempt) => attempt == 1 ? busy('3') : http.Response('', 204)), isTrue);
    expect(attempts, 2);
    expect(waits, [const Duration(seconds: 3)]);
  });

  test('a gate that stays busy gives up at the budget with bounded attempts', () async {
    expect(await delete((_) => busy('2')), isFalse);
    expect(waits, everyElement(const Duration(seconds: 2)));
    expect(waits.fold(Duration.zero, (a, b) => a + b), lessThanOrEqualTo(conversationDeleteRetryBudget));
    expect(attempts, 16); // t = 0, 2, …, 30 s
  });

  test('500 and a missing response fail without retrying', () async {
    expect(await delete((_) => http.Response('', 500)), isFalse);
    expect(attempts, 1);
    attempts = 0;
    expect(await delete((_) => null), isFalse);
    expect(attempts, 1);
    expect(waits, isEmpty);
  });

  test('Retry-After is clamped to 1–10 s and defaults to 2 s', () {
    DateTime now() => clock;
    expect(conversationDeleteRetryDelay(busy('0'), now), const Duration(seconds: 1));
    expect(conversationDeleteRetryDelay(busy('60'), now), const Duration(seconds: 10));
    expect(conversationDeleteRetryDelay(busy(), now), const Duration(seconds: 2));
    expect(conversationDeleteRetryDelay(busy('soon'), now), const Duration(seconds: 2));
  });
}
