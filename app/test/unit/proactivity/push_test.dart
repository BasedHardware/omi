import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/proactivity/proactivity_push.dart';
import '../../helpers/proactivity_fakes.dart';

void main() {
  const push = {
    'notification_type': 'proactivity_v2',
    'item_id': 'item-1',
    'target_kind': 'conversation',
    'target_id': 'conversation-1'
  };
  test('v2 push opens canonical conversation then records opened/push', () async {
    final h = OutcomeHarness();
    addTearDown(h.outbox.dispose);
    await h.bind();
    String? route;
    expect(
        await ProactivityPush.handle(push, outbox: h.outbox, open: (r, {canOpen}) async {
          expect(h.events, isEmpty);
          route = r;
          return true;
        }),
        isTrue);
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
        isFalse);
    String? route;
    await ProactivityPush.handle({...push, 'navigate_to': '/chat/mentor'}, outbox: h.outbox,
        open: (r, {canOpen}) async {
      route = r;
      return true;
    });
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
        await ProactivityPush.handle(push, outbox: h.outbox, open: (r, {canOpen}) async {
          await h.bind('owner-b');
          expect(canOpen!(), isFalse);
          return true;
        }),
        isFalse);
    expect(h.events, isEmpty);
  });
}
