import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/proactivity/proactivity_push.dart';
import '../../helpers/proactivity_fakes.dart';

void main() {
  const push = {
    'notification_type': 'proactivity_v2',
    'item_id': 'item-1',
    'target_kind': 'conversation',
    'target_id': 'conversation-1',
  };
  test('v2 push opens canonical conversation then records opened/push', () async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await h.bind();
    String? route;
    expect(
      await ProactivityPush.handle(
        push,
        outbox: h.outbox,
        open: (r, {canOpen}) async {
          expect(h.events, isEmpty);
          route = r;
          return true;
        },
      ),
      isTrue,
    );
    await Future<void>.delayed(Duration.zero);
    expect(route, '/conversation/conversation-1');
    expect(h.events.single.action, 'opened');
    expect(h.events.single.channel, 'push');
  });
  test('mentor v2 retains chat route; legacy mentor is not intercepted', () async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await h.bind();
    expect(
      ProactivityPush.matches({'notification_type': 'plugin', 'plugin_id': 'mentor', 'navigate_to': '/chat/mentor'}),
      isFalse,
    );
    String? route;
    await ProactivityPush.handle(
      {...push, 'navigate_to': '/chat/mentor'},
      outbox: h.outbox,
      open: (r, {canOpen}) async {
        route = r;
        return true;
      },
    );
    expect(route, '/chat/mentor');
  });
  test('missing/failed target and malformed push never record opened', () async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await h.bind();
    expect(await ProactivityPush.handle(push, outbox: h.outbox, open: (r, {canOpen}) async => false), isFalse);
    expect(await ProactivityPush.handle({...push, 'target_kind': 'url'}, outbox: h.outbox), isFalse);
    expect(await ProactivityPush.handle({...push, 'item_id': null}, outbox: h.outbox), isFalse);
    expect(h.events, isEmpty);
  });
  test('account switch during target loading fences navigation and outcome', () async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await h.bind();
    expect(
      await ProactivityPush.handle(
        push,
        outbox: h.outbox,
        open: (r, {canOpen}) async {
          await h.bind('owner-b');
          expect(canOpen!(), isFalse);
          return true;
        },
      ),
      isFalse,
    );
    expect(h.events, isEmpty);
  });
  test('cold-start tap waits for authenticated binding before navigation', () async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await h.bind(null);
    var opens = 0;
    final pending = ProactivityPush.handle(
      push,
      outbox: h.outbox,
      ownerTimeout: const Duration(seconds: 1),
      pollInterval: const Duration(milliseconds: 1),
      open: (r, {canOpen}) async {
        opens++;
        return true;
      },
    );
    expect(opens, 0);
    await h.bind();
    expect(await pending, isTrue);
    expect(opens, 1);
    await Future<void>.delayed(Duration.zero);
    expect(h.events.single.channel, 'push');
  });
  test('signed-out tap is dropped without opening or recording after wait expires', () async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await h.bind(null);
    expect(
      await ProactivityPush.handle(
        push,
        outbox: h.outbox,
        ownerTimeout: Duration.zero,
        open: (r, {canOpen}) async => throw StateError('Must not navigate'),
      ),
      isFalse,
    );
    expect(h.events, isEmpty);
  });
}
