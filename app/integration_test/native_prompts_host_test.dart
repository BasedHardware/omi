import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/models/announcement.dart';
import 'package:omi/pages/announcements/announcement_dialog.dart';
import 'package:omi/pages/announcements/changelog_sheet.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

/// Host checks for the prompts-first-run batch: run on Simulator with OMI_APP_PROFILE=local_dev and
/// OMI_IOS_SWIFTUI=true, on an iPhone 15-class (or taller) display: the announcement dialog is 80% of
/// the screen height and the harness expects more than 550 points.
void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('the prompt queue shows the native announcement, then the native changelog', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      late BuildContext home;
      await tester.pumpWidget(nativeHostApp(Builder(builder: (context) {
        home = context;
        return const Scaffold(body: SizedBox.expand());
      })));
      final queue = PromptQueue(contextProvider: () => home);
      AnnouncementOutcome? outcome;
      var changelogShown = false;
      queue.enqueue('announcement-native-host', PromptPriority.normal,
          show: (context) async => outcome = await AnnouncementDialog.show(context, _announcement));
      queue.enqueue('changelog-native-host', PromptPriority.normal, show: (context) async {
        changelogShown = true;
        await ChangelogSheet.show(context, [_changelog('1.0.2'), _changelog('1.0.1')]);
      });
      await tester.pump();
      await checkNativeHost(tester, 'native-prompts-first-run-announcement-dark');
      expect(queue.showingId, 'announcement-native-host');
      expect(changelogShown, isFalse, reason: 'one prompt at a time');
      await nativeProjectedRow(tester, 'announcement_not_now').action!(null);
      await tester.pumpAndSettle();
      expect(outcome, AnnouncementOutcome.notNow);

      await checkNativeHost(tester, 'native-prompts-first-run-changelog-dark');
      expect(queue.showingId, 'changelog-native-host');
      expect(nativeProjectedRow(tester, 'changelog_version').value, '1');
      await nativeProjectedRow(tester, 'changelog_close').action!(null);
      await tester.pumpAndSettle();
      expect(queue.showingId, isNull);
    });

    testWidgets("Settings What's New opens the native changelog with fixture data", (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      await tester.pumpWidget(nativeHostApp(Builder(
          builder: (context) => Scaffold(
              body: Center(
                  child: TextButton(
                      // The Settings destination's loader (at most five versions), with fixture data
                      // instead of the network.
                      onPressed: () => ChangelogSheet.showWithLoading(
                          context, () async => [for (var i = 5; i >= 1; i--) _changelog('1.0.$i')]),
                      child: const Text('whats-new')))))));
      await tester.tap(find.text('whats-new'));
      await tester.pump();
      await checkNativeHost(tester, 'native-prompts-first-run-whats-new-dark');
      expect(nativeProjectedRow(tester, 'changelog_version').value, '4');
      await nativeProjectedRow(tester, 'changelog_version').action!('3');
      await tester.pump();
      expect(nativeProjectedRow(tester, 'changelog_version').value, '3');
      expect(nativeProjectedRow(tester, 'changelog_item_0').title, '🚀 Change in 1.0.4');
    });
  });
}

final _announcement = Announcement.fromJson({
  'id': 'native-host-announcement',
  'type': 'announcement',
  'created_at': '2026-09-01T00:00:00Z',
  'active': true,
  'content': {
    'title': 'Meet Omi Memories',
    'body': 'Everything you said, remembered.',
    'cta': {'text': 'Open Memories', 'action': 'navigate:/memories'},
  },
});

Announcement _changelog(String version) => Announcement.fromJson({
      'id': 'native-host-changelog-$version',
      'type': 'changelog',
      'created_at': '2026-09-01T00:00:00Z',
      'active': true,
      'app_version': version,
      'content': {
        'title': 'Release $version',
        'changes': [
          {'title': 'Change in $version', 'description': 'Details for $version', 'icon': '🚀'},
        ],
      },
    });
