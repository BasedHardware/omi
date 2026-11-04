// Named demo walks. Add a page by registering an AuditScenario (app/e2e/SKILL.md, Visual audit),
// then add a [DemoWalkStep] here. app/scripts/demo_walk.sh records the walk.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/ui/ui.dart';

import 'harness.dart';

/// One recording. [steps] run in order on a single navigator, so each page pushes with the app's
/// route transition.
class DemoWalk {
  const DemoWalk({required this.id, required this.title, required this.steps});

  final String id;
  final String title;
  final List<DemoWalkStep> steps;
}

/// [scenarioId] is an id from the visual-audit registry. [tap] presses that visible label after
/// the page has settled. [afterTap] is text that tap must reveal; the walk then holds
/// [_afterTapHold] so the revealed panel can be read. [revealPlans] waits for the plans sheet and
/// checks it rendered the demo catalog instead of the load-failure state. [pops] then closes that
/// many routes (the sheet is one; a sheet on top of Plan & Usage is two).
class DemoWalkStep {
  const DemoWalkStep(this.scenarioId, {this.tap, this.afterTap, this.revealPlans = false, this.pops = 0});

  final String scenarioId;
  final String? tap;
  final String? afterTap;
  final bool revealPlans;
  final int pops;
}

/// Long enough to read the expanded on-device why. Independent of the per-frame hold, which is
/// too short for that paragraph.
const _afterTapHold = Duration(seconds: 4);

/// The UI-cleanup surfaces: home, locked rows, the plans mock, search, activity, memories,
/// Plan & Usage, live, On the Way, Offline Sync, the iPhone summary line, Device, onboarding,
/// Dream Report, and recent changes.
const uiCleanupWalk = DemoWalk(
  id: 'ui-cleanup',
  title: 'UI cleanup walk',
  steps: [
    DemoWalkStep('review-entry-home'),
    DemoWalkStep('conversations-locked-preview', tap: 'Upgrade', revealPlans: true, pops: 1),
    DemoWalkStep('search-results'),
    DemoWalkStep('activity'),
    DemoWalkStep('memories-locked', tap: 'Upgrade', revealPlans: true, pops: 2),
    DemoWalkStep('settings-usage'),
    DemoWalkStep('conversation-live-phone-paused'),
    DemoWalkStep('on-the-way'),
    DemoWalkStep('conversations-offline-sync-history'),
    DemoWalkStep(
      'conversation-iphone-summary',
      tap: 'Transcribed and summarized on this iPhone',
      afterTap: 'Why this was done on your phone',
    ),
    DemoWalkStep('device-catching-up-large'),
    DemoWalkStep('onboarding-find-devices-none'),
    DemoWalkStep('review-dream-report'),
    DemoWalkStep('review-recent-changes'),
  ],
);

const demoWalks = <DemoWalk>[uiCleanupWalk];

DemoWalk demoWalkById(String id) {
  for (final walk in demoWalks) {
    if (walk.id == id) return walk;
  }
  throw ArgumentError('Unknown demo walk "$id". Known: ${demoWalks.map((w) => w.id).join(', ')}');
}

/// Plays [walk] on the already-booted hermetic host. Fails if a page throws or the plans sheet
/// renders the load-failure state.
Future<void> playDemoWalk({required WidgetTester tester, required AuditSuite suite, required DemoWalk walk}) async {
  final byId = {for (final scenario in suite.scenarios) scenario.id: scenario};
  for (final step in walk.steps) {
    final scenario = byId[step.scenarioId];
    if (scenario == null) fail('Demo walk ${walk.id} names unknown scenario ${step.scenarioId}');
    walkLog('DEMO_WALK_BEAT ${step.scenarioId}');
    await driveWalkScenario(tester, suite, scenario);
    if (step.tap != null) {
      final finder = find.text(step.tap!);
      expect(finder, findsWidgets, reason: '${step.scenarioId} should show "${step.tap}"');
      await tester.tap(finder.hitTestable().first, warnIfMissed: false);
      await _until(tester, step.revealPlans ? find.text('Upgrade Your Plan') : finder);
      expect(tester.takeException(), isNull, reason: '${step.scenarioId} tap ${step.tap}');
      if (step.afterTap != null) {
        final revealed = find.text(step.afterTap!);
        await _until(tester, revealed);
        expect(revealed, findsWidgets, reason: '${step.scenarioId} tap did not reveal "${step.afterTap}"');
        expect(tester.takeException(), isNull, reason: '${step.scenarioId} ${step.afterTap}');
        await Future<void>.delayed(_afterTapHold);
        await tester.pump();
        expect(tester.takeException(), isNull, reason: '${step.scenarioId} hold ${step.afterTap}');
      }
      if (step.revealPlans) {
        expect(find.text('Unable to load plans'), findsNothing, reason: '${step.scenarioId} plans failed to load');
        expect(find.byType(OmiErrorState), findsNothing, reason: '${step.scenarioId} showed an error state');
        await _scrollPlans(tester);
        expect(find.text('Omi Pro'), findsWidgets, reason: '${step.scenarioId} plans catalog did not render');
        await Future<void>.delayed(auditWalkShotHold);
        await tester.pump();
        expect(tester.takeException(), isNull, reason: '${step.scenarioId} plans sheet');
      }
      for (var i = 0; i < step.pops; i++) {
        final nav = globalNavigatorKey.currentState;
        if (nav != null && nav.canPop()) nav.pop();
        await Future<void>.delayed(const Duration(milliseconds: 420));
        await tester.pump();
      }
    }
  }
}

Future<void> _until(WidgetTester tester, Finder finder) async {
  final deadline = DateTime.now().add(const Duration(seconds: 5));
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump();
    final error = tester.takeException();
    if (error != null) fail('$error');
    if (finder.evaluate().isNotEmpty) return;
    await Future<void>.delayed(const Duration(milliseconds: 150));
  }
  fail('Timed out waiting for $finder');
}

Future<void> _scrollPlans(WidgetTester tester) async {
  final lists = find.byType(Scrollable);
  if (lists.evaluate().isEmpty) return;
  final position = tester.state<ScrollableState>(lists.last).position;
  final target = position.pixels + 520;
  if (target <= position.maxScrollExtent) {
    position.animateTo(target, duration: const Duration(milliseconds: 800), curve: Curves.easeOut);
  }
  await Future<void>.delayed(const Duration(milliseconds: 900));
  await tester.pump();
}
