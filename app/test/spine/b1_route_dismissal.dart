import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// A pop result precedes reverse animation and overlay disposal. Advance frames
/// until THIS route completes, independently of unrelated repeating animations.
Future<void> expectRouteDismissed(
  WidgetTester tester,
  ModalRoute<dynamic> route,
  Element page,
  FutureOr<void> Function() dismiss,
) async {
  expect(route.isCurrent, isTrue, reason: 'dismiss the actual foreground route');
  var completed = false;
  unawaited(route.completed.then((_) => completed = true));
  await dismiss();
  // The first frame establishes a ticker started between frames; a single pump
  // with a duration does not simulate the intervening animation frames.
  await tester.pump();
  expect(route.isActive, isFalse, reason: 'the control must pop its own route');
  final deadline = tester.binding.clock.now().add(route.reverseTransitionDuration + const Duration(seconds: 1));
  while (!completed && tester.binding.clock.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  expect(completed, isTrue, reason: 'dismissed route must finish its transition and release its overlay');
  expect(page.mounted, isFalse, reason: 'dismissed page must be disposed, not merely hidden');
}
