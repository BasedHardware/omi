import 'dart:async';

import 'package:omi/backend/schema/gen/proactivity_wire.g.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/services/proactivity/proactivity_outbox.dart';
import 'package:omi/services/proactivity/proactivity_runtime.dart';

typedef ProactivityTargetOpener = Future<bool> Function(String route, {bool Function()? canOpen});

String? proactivityTargetRoute(GeneratedProactivityTarget target) {
  if (target.id.isEmpty) return null;
  final alias = switch (target.kind) {
    'conversation' => 'conversation',
    'action_item' => 'task',
    _ => null,
  };
  return alias == null ? null : '/$alias/${Uri.encodeComponent(target.id)}';
}

Future<bool> openProactivityTarget(
  String itemId,
  GeneratedProactivityTarget target, {
  required ProactivityOutbox outbox,
  String channel = 'feed',
  String? routeOverride,
  ProactivityTargetOpener? open,
}) async {
  final epoch = outbox.epoch;
  final route = proactivityTargetRoute(target);
  if (route == null || !outbox.isCurrent(epoch)) return false;
  try {
    final opened = await (open ?? HomeNavigation.openRoute)(
      routeOverride ?? route,
      canOpen: () => outbox.isCurrent(epoch),
    );
    if (!opened || !outbox.isCurrent(epoch)) return false;
    await outbox.record(itemId, ProactivityAction.opened, channel: channel);
    return true;
  } catch (_) {
    return false;
  }
}

/// The spine's generic v2 push carries only identity. Legacy plugin taps use
/// their original dispatcher. Mentor v2 retains the spine's canonical chat route.
abstract final class ProactivityPush {
  static bool matches(Map<String, dynamic> data) => data['notification_type'] == 'proactivity_v2';

  static Future<bool> handle(
    Map<String, dynamic> data, {
    ProactivityOutbox? outbox,
    ProactivityTargetOpener? open,
    Duration ownerTimeout = const Duration(seconds: 15),
    Duration pollInterval = const Duration(milliseconds: 50),
  }) async {
    final id = data['item_id'];
    final kind = data['target_kind'];
    final targetId = data['target_id'];
    if (!matches(data) || id is! String || id.isEmpty || kind is! String || targetId is! String) return false;
    final receipts = outbox ?? ProactivityRuntime.outbox;
    // getInitialMessage can arrive before preferences and AuthProvider mount.
    // Wait for the normal authenticated binding; never bypass sign-in/onboarding.
    final deadline = DateTime.now().add(ownerTimeout);
    while (!receipts.isCurrent(receipts.epoch) && DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(pollInterval);
    }
    if (!receipts.isCurrent(receipts.epoch)) return false;
    return openProactivityTarget(
      id,
      GeneratedProactivityTarget(kind: kind, id: targetId),
      outbox: receipts,
      channel: 'push',
      routeOverride: data['navigate_to'] == '/chat/mentor' ? '/chat/mentor' : null,
      open: open,
    );
  }
}
