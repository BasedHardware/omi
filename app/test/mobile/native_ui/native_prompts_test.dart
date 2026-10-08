import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/pages/announcements/announcement_dialog.dart';
import 'package:omi/pages/announcements/changelog_sheet.dart';
import 'package:omi/pages/announcements/feature_screen.dart';
import 'package:omi/pages/onboarding/permissions/onboarding_permissions_panel.dart';
import 'package:omi/pages/onboarding/permissions/permissions_checker.dart';
import 'package:omi/pages/onboarding/setup_page.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/alerts/app_dialog.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/widgets/upgrade_alert.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');

Announcement _announcement({String? imageUrl, Map<String, Object>? cta}) => Announcement.fromJson({
      'id': 'a-1',
      'type': 'announcement',
      'created_at': '2026-09-01T00:00:00Z',
      'active': true,
      'content': {
        'title': 'Meet *Omi* Memories',
        'body': 'Everything you said, [remembered](https://evil.example).',
        if (imageUrl != null) 'image_url': imageUrl,
        if (cta != null) 'cta': cta,
      },
    });

Announcement _feature(List<Map<String, Object>> steps) => Announcement.fromJson({
      'id': 'f-1',
      'type': 'feature',
      'created_at': '2026-09-01T00:00:00Z',
      'active': true,
      'content': {'title': 'Tasks', 'steps': steps},
    });

Announcement _changelog(String version) => Announcement.fromJson({
      'id': 'c-$version',
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

/// The newest snapshot the native view [id] received: its last 'update', else its creation params.
Map _snapshot(WidgetTester tester, NativeTestHost host) {
  final updates = host.calls.where((call) => call.$2.method == 'update').toList();
  if (updates.isNotEmpty) return updates.last.$2.arguments as Map;
  return tester.widget<UiKitView>(find.byType(UiKitView)).creationParams as Map;
}

List<Map> _rows(Map snapshot) =>
    [for (final section in (snapshot['sections'] as List).cast<Map>()) ...(section['rows'] as List).cast<Map>()];

List<String> _ids(Iterable<Map> rows) => rows.map((row) => row['id'] as String).toList();

Future<void> _send(WidgetTester tester, NativeTestHost host, String id, [Object? value]) async {
  await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
  await NativeTestHost.settle(tester);
}

/// Answers every 'present' on the config channel with [reply]; a [PlatformException] is thrown.
List<Map> _answerPresentations(Object? Function(Map request) reply) {
  final presented = <Map>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method != 'present') return null;
    presented.add(call.arguments as Map);
    final answer = reply(call.arguments as Map);
    if (answer is PlatformException) throw answer;
    return answer;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

/// A host page whose button runs [open] with a context under the app's navigator.
Widget _launcher(void Function(BuildContext context) open) => NativeTestHost.app(Builder(
    builder: (context) =>
        Scaffold(body: Center(child: TextButton(onPressed: () => open(context), child: const Text('open'))))));

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('announcement', () {
    Future<(NativeTestHost, Future<AnnouncementOutcome> Function())> open(WidgetTester tester,
        {Announcement? announcement}) async {
      final host = NativeTestHost.install();
      Future<AnnouncementOutcome>? outcome;
      await tester.pumpWidget(
          _launcher((context) => outcome = AnnouncementDialog.show(context, announcement ?? _announcement())));
      await tester.tap(find.text('open'));
      await NativeTestHost.settle(tester);
      expect(find.byType(UiKitView), findsOneWidget);
      return (host, () => outcome!);
    }

    final cta = {'text': 'Open it', 'action': 'https://omi.me/memories'};

    testWidgets('the CTA answers cta and marks it seen', (tester) async {
      final (host, outcome) = await open(tester, announcement: _announcement(cta: cta));
      expect(_ids(_rows(_snapshot(tester, host))), ['announcement_body', 'announcement_cta', 'announcement_not_now']);
      await _send(tester, host, 'announcement_cta');
      await tester.pumpAndSettle();
      expect(await outcome(), AnnouncementOutcome.cta);
      expect(AnnouncementOutcome.cta.marksSeen, isTrue);
    });

    testWidgets('the toolbar close answers closed and marks it seen', (tester) async {
      final (host, outcome) = await open(tester);
      expect(_ids((_snapshot(tester, host)['toolbar'] as List).cast<Map>()), ['announcement_close']);
      expect(_ids(_rows(_snapshot(tester, host))), isNot(contains('announcement_cta')), reason: 'no CTA, no button');
      await _send(tester, host, 'announcement_close');
      await tester.pumpAndSettle();
      expect(await outcome(), AnnouncementOutcome.closed);
      expect(AnnouncementOutcome.closed.marksSeen, isTrue);
    });

    testWidgets('Not Now postpones without marking it seen, and a repeated command pops nothing else', (tester) async {
      final (host, outcome) = await open(tester);
      final viewId = host.created.last;
      await host.sendFromNative(viewId, const MethodCall('action', {'id': 'announcement_not_now', 'value': null}));
      await host.sendFromNative(viewId, const MethodCall('action', {'id': 'announcement_not_now', 'value': null}));
      await tester.pumpAndSettle();
      expect(await outcome(), AnnouncementOutcome.notNow);
      expect(AnnouncementOutcome.notNow.marksSeen, isFalse);
      expect(find.text('open'), findsOneWidget, reason: 'the launcher route beneath stays');
    });

    testWidgets('system back answers none', (tester) async {
      final (_, outcome) = await open(tester);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(await outcome(), AnnouncementOutcome.none);
      expect(AnnouncementOutcome.none.marksSeen, isFalse);
    });

    testWidgets('server text stays literal and only an HTTPS image crosses', (tester) async {
      final (host, _) = await open(tester, announcement: _announcement(imageUrl: 'https://cdn.omi.me/a.png'));
      final body = _rows(_snapshot(tester, host)).firstWhere((row) => row['id'] == 'announcement_body');
      final blocks = (body['blocks'] as List).cast<Map>();
      expect(blocks.map((block) => block['kind']), ['image', 'heading', 'text']);
      expect(blocks.first['uri'], 'https://cdn.omi.me/a.png');
      expect(blocks[1]['text'], r'Meet \*Omi\* Memories');
      expect(blocks[2]['text'], r'Everything you said, \[remembered\](https://evil.example).');
      expect(body['options'], isEmpty, reason: 'no link reaches an owner');
    });

    testWidgets('a non-HTTPS image is dropped, not the announcement', (tester) async {
      final (host, _) = await open(tester, announcement: _announcement(imageUrl: 'http://cdn.omi.me/a.png'));
      final body = _rows(_snapshot(tester, host)).firstWhere((row) => row['id'] == 'announcement_body');
      expect((body['blocks'] as List).cast<Map>().map((block) => block['kind']), ['heading', 'text']);
    });

    test('image blocks accept HTTPS only', () {
      expect(nativeAnnouncementImageBlock('https://cdn.omi.me/a.png'), isNotNull);
      expect(nativeAnnouncementImageBlock('http://cdn.omi.me/a.png'), isNull);
      expect(nativeAnnouncementImageBlock('file:///tmp/a.png'), isNull);
      expect(nativeAnnouncementImageBlock('https://user:pw@cdn.omi.me/a.png'), isNull);
      expect(nativeAnnouncementImageBlock(null), isNull);
      // Spellings Swift's URL parser reads differently are dropped rather than refusing the surface.
      expect(nativeAnnouncementImageBlock('HTTPS://cdn.omi.me/a.png'), isNull);
      expect(nativeAnnouncementImageBlock('https://cdn.omi.me/a b.png'), isNull);
    });

    test('the CTA allowlist is unchanged: navigate:/route, /route and http(s) pages only', () {
      expect((AnnouncementAction.parse('navigate:/memories') as AnnouncementRoute).route, '/memories');
      expect((AnnouncementAction.parse('navigate:memories') as AnnouncementRoute).route, '/memories');
      expect((AnnouncementAction.parse('/apps') as AnnouncementRoute).route, '/apps');
      expect((AnnouncementAction.parse('url:https://omi.me') as AnnouncementUrl).uri.host, 'omi.me');
      expect((AnnouncementAction.parse('http://omi.me') as AnnouncementUrl).uri.host, 'omi.me');
      expect(AnnouncementAction.parse('tel:+15550100'), isNull);
      expect(AnnouncementAction.parse('file:///etc/hosts'), isNull);
      expect(AnnouncementAction.parse('omi://settings'), isNull);
      expect(AnnouncementAction.parse('navigate:'), isNull);
    });
  });

  group('feature screen', () {
    Future<(NativeTestHost, Future<AnnouncementOutcome> Function())> open(
        WidgetTester tester, Announcement feature) async {
      final host = NativeTestHost.install();
      Future<AnnouncementOutcome>? outcome;
      await tester.pumpWidget(_launcher((context) => outcome = FeatureScreen.show(context, feature)));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);
      return (host, () => outcome!);
    }

    List<String> toolbar(WidgetTester tester, NativeTestHost host) =>
        _ids((_snapshot(tester, host)['toolbar'] as List).cast<Map>());
    List<String> sections(WidgetTester tester, NativeTestHost host) =>
        (_snapshot(tester, host)['sections'] as List).cast<Map>().map((section) => section['id'] as String).toList();

    testWidgets('paged mode shows one step at a time with a page picker, Continue and Got It', (tester) async {
      final (host, outcome) = await open(
          tester,
          _feature([
            {'title': 'One', 'description': 'First', 'image_url': 'https://cdn.omi.me/1.png'},
            {'title': 'Two', 'description': 'Second', 'video_url': 'https://cdn.omi.me/2.mp4'},
            {'title': 'Three', 'description': 'Third', 'image_url': 'http://cdn.omi.me/3.png'},
          ]));
      expect(sections(tester, host), ['feature_pages', 'feature_step_0']);
      expect(toolbar(tester, host), ['feature_close', 'feature_next']);
      final picker = _rows(_snapshot(tester, host)).firstWhere((row) => row['id'] == 'feature_page');
      expect(picker['kind'], 'segmented');
      expect(picker['value'], '0');

      await _send(tester, host, 'feature_next');
      expect(sections(tester, host), ['feature_pages', 'feature_step_1']);
      final video = _rows(_snapshot(tester, host)).firstWhere((row) => row['id'] == 'feature_video_1');
      expect([video['kind'], video['symbol']], ['label', 'play.rectangle']);

      await _send(tester, host, 'feature_page', '2');
      expect(sections(tester, host), ['feature_pages', 'feature_step_2']);
      expect(toolbar(tester, host), ['feature_close', 'feature_done']);
      final body = _rows(_snapshot(tester, host)).firstWhere((row) => row['id'] == 'feature_step_body_2');
      expect((body['blocks'] as List).cast<Map>().map((block) => block['kind']), ['heading', 'text'],
          reason: 'the plain HTTP image is dropped');

      await _send(tester, host, 'feature_done');
      await tester.pumpAndSettle();
      expect(await outcome(), AnnouncementOutcome.closed);
    });

    testWidgets('list mode numbers every step on one page and closes with Got It', (tester) async {
      final (host, outcome) = await open(
          tester,
          _feature([
            {'title': 'Capture', 'description': 'Say it out loud', 'highlight_text': 'out loud'},
            {'title': 'Review', 'description': 'Check the list'},
          ]));
      expect(sections(tester, host), ['feature_step_0', 'feature_step_1']);
      expect(toolbar(tester, host), ['feature_close', 'feature_done']);
      final blocks =
          (_rows(_snapshot(tester, host)).firstWhere((row) => row['id'] == 'feature_step_body_0')['blocks'] as List)
              .cast<Map>();
      expect(blocks[0]['prefix'], '1.');
      expect(blocks[1]['text'], 'Say it **out loud**');

      await _send(tester, host, 'feature_close');
      await tester.pumpAndSettle();
      expect(await outcome(), AnnouncementOutcome.closed);
    });

    test('a highlight is bolded once, with its spaces outside the emphasis and server text escaped', () {
      FeatureStep step(String description, String? highlight) =>
          FeatureStep(title: 't', description: description, highlightText: highlight);
      expect(nativeFeatureDescription(step('Tap the * button now', ' the * button ')), r'Tap **the \* button** now');
      expect(nativeFeatureDescription(step('a b a', 'a')), '**a** b a');
      expect(nativeFeatureDescription(step('plain_text', 'missing')), r'plain\_text');
      expect(nativeFeatureDescription(step('plain', '  ')), 'plain');
      // Emphasis that CommonMark would not open or close stays plain rather than showing stars.
      expect(nativeFeatureDescription(step('Try Omi(beta) now', '(beta)')), 'Try Omi(beta) now');
      expect(nativeFeatureDescription(step('Try Omi (beta) now', '(beta)')), 'Try Omi **(beta)** now');
    });
  });

  group('changelog', () {
    Future<NativeTestHost> mount(WidgetTester tester, List<Announcement> changelogs) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(NativeTestHost.app(Scaffold(body: ChangelogSheet(changelogs: changelogs, native: true))));
      await NativeTestHost.settle(tester);
      return host;
    }

    testWidgets('up to five versions pick from a segmented control, newest first shown', (tester) async {
      // The server sends newest first.
      final host = await mount(tester, [_changelog('1.0.3'), _changelog('1.0.2'), _changelog('1.0.1')]);
      var snapshot = _snapshot(tester, host);
      expect(snapshot['title'], "What's New in 1.0.3");
      final picker = _rows(snapshot).firstWhere((row) => row['id'] == 'changelog_version');
      expect(picker['value'], '2');
      expect((picker['options'] as List).cast<Map>().map((option) => option['title']),
          ['Version 1.0.1', 'Version 1.0.2', 'Version 1.0.3']);
      final item = _rows(snapshot).firstWhere((row) => row['id'] == 'changelog_item_0');
      expect([item['title'], item['subtitle']], ['🚀 Change in 1.0.3', 'Details for 1.0.3']);

      await _send(tester, host, 'changelog_version', '0');
      snapshot = _snapshot(tester, host);
      expect(snapshot['title'], "What's New in 1.0.1");
      expect(_rows(snapshot).firstWhere((row) => row['id'] == 'changelog_item_0')['title'], '🚀 Change in 1.0.1');
    });

    testWidgets('more than five versions page with previous and next around the version label', (tester) async {
      final host = await mount(tester, [for (var i = 6; i >= 1; i--) _changelog('2.0.$i')]);
      var rows = _rows(_snapshot(tester, host));
      expect(_ids(rows).take(3), ['changelog_previous', 'changelog_version_label', 'changelog_next']);
      expect(rows.firstWhere((row) => row['id'] == 'changelog_next')['enabled'], isFalse, reason: 'already newest');
      await _send(tester, host, 'changelog_previous');
      rows = _rows(_snapshot(tester, host));
      expect(rows.firstWhere((row) => row['id'] == 'changelog_version_label')['title'], 'Version 2.0.5');
      expect(rows.firstWhere((row) => row['id'] == 'changelog_next')['enabled'], isTrue);
    });

    testWidgets('a repeated close pops only the changelog', (tester) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(_launcher((context) => Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) => Scaffold(body: ChangelogSheet(changelogs: [_changelog('1.0.1')], native: true))))));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);
      final viewId = host.created.last;
      await host.sendFromNative(viewId, const MethodCall('action', {'id': 'changelog_close', 'value': null}));
      await tester.pump();
      await host.sendFromNative(viewId, const MethodCall('action', {'id': 'changelog_close', 'value': null}));
      await tester.pumpAndSettle();
      expect(find.byType(ChangelogSheet), findsNothing);
      expect(find.text('open'), findsOneWidget, reason: 'the route beneath stays');
    });

    testWidgets('a failed load shows the error with Retry, which reloads through the same loader', (tester) async {
      final host = NativeTestHost.install();
      var calls = 0;
      await tester.pumpWidget(NativeTestHost.app(Scaffold(
          body: ChangelogSheet(
              native: true,
              changelogsFuture: () async {
                calls++;
                if (calls == 1) throw Exception('offline');
                return [_changelog('1.0.1')];
              }))));
      await NativeTestHost.settle(tester);
      var snapshot = _snapshot(tester, host);
      expect([snapshot['failed'], snapshot['refreshEnabled']], [true, true]);
      expect(snapshot['error'], "Couldn't load what's new");
      await host.sendFromNative(host.created.last, const MethodCall('action', {'id': '_refresh', 'value': null}));
      await NativeTestHost.settle(tester);
      snapshot = _snapshot(tester, host);
      expect(calls, 2);
      expect([snapshot['failed'], snapshot['loading'], snapshot['refreshEnabled']], [false, false, false],
          reason: 'loaded content offers no reload');
      expect(_ids(_rows(snapshot)), ['changelog_item_0']);
    });

    testWidgets('a single version has no version picker', (tester) async {
      final host = await mount(tester, [_changelog('1.0.1')]);
      expect(_ids(_rows(_snapshot(tester, host))), ['changelog_item_0']);
    });
  });

  group('update prompt', () {
    testWidgets('a required update cannot be dismissed and Update keeps it open', (tester) async {
      final host = NativeTestHost.install();
      var updates = 0;
      var later = 0;
      await tester.pumpWidget(_launcher((context) => Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) =>
              UpdatePromptSheet(required: true, native: true, onUpdate: () => updates++, onLater: () => later++)))));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);
      final ids = _ids(_rows(_snapshot(tester, host)));
      expect(ids, containsAll(['update_title', 'update_message', 'update_now']));
      expect(ids, isNot(contains('update_not_now')));

      await _send(tester, host, 'update_now');
      expect(updates, 1);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.byType(UpdatePromptSheet), findsOneWidget, reason: 'back does not close a required update');
      expect(later, 0);
    });

    testWidgets('an optional update offers Not Now and its release notes', (tester) async {
      final host = NativeTestHost.install();
      var later = 0;
      await tester.pumpWidget(NativeTestHost.app(UpdatePromptSheet(
          required: false,
          native: true,
          releaseNotes: '• Faster sync\n- Fixes\nThird',
          onUpdate: () {},
          onLater: () => later++)));
      await NativeTestHost.settle(tester);
      final rows = _rows(_snapshot(tester, host));
      expect(_ids(rows),
          ['update_title', 'update_message', 'update_note_0', 'update_note_1', 'update_now', 'update_not_now']);
      expect(rows.firstWhere((row) => row['id'] == 'update_note_0')['title'], 'Faster sync');
      await _send(tester, host, 'update_not_now');
      expect(later, 1);
    });
  });

  group('AppDialog', () {
    Future<void> show(WidgetTester tester, {required bool singleButton, required List<String> log}) async {
      NativeTestHost.install();
      await tester.pumpWidget(NativeTestHost.app(Navigator(
          key: globalNavigatorKey, onGenerateRoute: (_) => MaterialPageRoute<void>(builder: (_) => const Scaffold()))));
      AppDialog.show(
          title: 'Error',
          content: 'Could not enable the app.',
          singleButton: singleButton,
          destructive: true,
          onConfirm: () => log.add('confirm'),
          onCancel: () => log.add('cancel'));
      await NativeTestHost.settle(tester);
    }

    for (final (reply, expected) in [
      ({'action': 'confirm', 'values': <String, Object?>{}, 'reason': 'action'}, ['confirm']),
      ({'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'}, ['cancel']),
      ({'action': null, 'values': <String, Object?>{}, 'reason': 'dismissed'}, <String>[]),
      ({'action': null, 'values': <String, Object?>{}, 'reason': 'programmatic'}, <String>[]),
    ]) {
      testWidgets('reason ${reply['reason']} runs $expected', (tester) async {
        final log = <String>[];
        final presented = _answerPresentations((_) => reply);
        await show(tester, singleButton: false, log: log);
        expect(presented, hasLength(1));
        final toolbar = ((presented.single['snapshot'] as Map)['toolbar'] as List).cast<Map>();
        expect(_ids(toolbar), ['cancel', 'confirm']);
        expect(toolbar.last['destructive'], isTrue);
        expect(log, expected);
        expect(find.byType(AlertDialog), findsNothing);
      });
    }

    testWidgets('single button acknowledges with onCancel', (tester) async {
      final log = <String>[];
      final presented =
          _answerPresentations((_) => {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'});
      await show(tester, singleButton: true, log: log);
      expect(presented.single['cancelId'], 'acknowledge');
      expect(_ids(((presented.single['snapshot'] as Map)['toolbar'] as List).cast<Map>()), ['acknowledge']);
      expect(log, ['cancel']);
    });

    testWidgets('a refused presentation keeps the Flutter dialog and its callbacks', (tester) async {
      final log = <String>[];
      _answerPresentations((_) => PlatformException(code: 'invalid_native_presentation'));
      await show(tester, singleButton: false, log: log);
      await tester.pumpAndSettle();
      expect(find.text('Could not enable the app.'), findsOneWidget);
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      expect(log, ['confirm']);
    });
  });

  group('onboarding setup', () {
    test('the rating alert maps support, cancel to notReally, and anything else to no answer', () {
      expect(nativeRatingAnswer(const NativeModalResult('support', {})),
          OnboardingSetupRatingPromptAnsweredAnswer.support);
      expect(
          nativeRatingAnswer(const NativeModalResult(null, {})), OnboardingSetupRatingPromptAnsweredAnswer.notReally);
      for (final reason in ['invalidated', 'unmounted', 'dismissed', 'programmatic']) {
        expect(nativeRatingAnswer(NativeModalResult(null, const {}, reason: reason)), isNull, reason: reason);
      }
    });

    testWidgets('the checklist and the rating alert are native; Not Really is cancel', (tester) async {
      PackageInfo.setMockInitialValues(
          appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.0', buildNumber: '1', buildSignature: '');
      AnalyticsManager.resetForTesting();
      final analytics = _Analytics();
      AnalyticsManager.configure(analytics);
      await AnalyticsManager.init();
      addTearDown(AnalyticsManager.resetForTesting);
      final host = NativeTestHost.install();
      final presented =
          _answerPresentations((_) => {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'});
      var reviews = 0;
      var finished = 0;
      await tester.pumpWidget(NativeTestHost.app(OnboardingSetupPage(
        onFinished: () => finished++,
        stepInterval: const Duration(milliseconds: 100),
        ratingPromptDelay: const Duration(milliseconds: 50),
        requestReview: () async => reviews++,
      )));
      await NativeTestHost.settle(tester);
      expect(_ids(_rows(_snapshot(tester, host))).where((id) => id.startsWith('onboarding_setup_step_')),
          hasLength(OnboardingSetupPage.stepCount));
      await tester.pump(const Duration(milliseconds: 60));
      await tester.pump();
      expect(presented, hasLength(1));
      expect(presented.single['cancelId'], 'not_really');
      expect(presented.single['dismissible'], isFalse);
      await tester.pump(const Duration(milliseconds: 500));
      await NativeTestHost.settle(tester);
      expect(_rows(_snapshot(tester, host)).firstWhere((row) => row['id'] == 'onboarding_setup_step_0')['symbol'],
          'checkmark.circle.fill');
      await tester.pump(const Duration(seconds: 2));
      expect(reviews, 0, reason: 'Not Really never opens the store review');
      expect(finished, 1);
      await tester.runAsync(() => AnalyticsManager.flushPending(force: true));
      const answered = OnboardingSetupRatingPromptAnswered(answer: OnboardingSetupRatingPromptAnsweredAnswer.notReally);
      expect(analytics.tracked.where((event) => event.$1 == answered.wireName).map((event) => event.$2?['answer']),
          [answered.properties['answer']],
          reason: 'cancel is answered as notReally, not as no answer');
    });
  });

  testWidgets('the permissions interstitial continues home through the existing owners', (tester) async {
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.0', buildNumber: '1', buildSignature: '');
    AnalyticsManager.resetForTesting();
    final analytics = _Analytics();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    addTearDown(AnalyticsManager.resetForTesting);
    final host = NativeTestHost.install();
    final source = _Permissions();
    await tester.pumpWidget(NativeTestHost.app(PermissionsInterstitialPage(source: source)));
    await NativeTestHost.settle(tester);
    expect(_ids(_rows(_snapshot(tester, host))), contains('onboarding_permissions_continue'));

    await host.sendFromNative(
        host.created.last, const MethodCall('action', {'id': 'onboarding_permissions_continue', 'value': null}));
    await host.sendFromNative(
        host.created.last, const MethodCall('action', {'id': 'onboarding_permissions_continue', 'value': null}));
    await tester.idle();
    await AnalyticsManager.flushPending(force: true);
    expect(source.requested, [OnboardingPermission.location, OnboardingPermission.notifications],
        reason: 'Continue asks once for what is missing');
    expect(analytics.events.where((event) => event == 'Permissions Interstitial Completed'), hasLength(1));
    expect(SharedPreferencesUtil().permissionsCompleted, isTrue, reason: 'then it goes home');
    await tester.pumpWidget(const SizedBox.shrink());
  });

  group('language', () {
    testWidgets('Save applies the selection once through the existing owner', (tester) async {
      final host = NativeTestHost.install();
      final home = _Home();
      addTearDown(home.dispose);
      await tester.pumpWidget(ChangeNotifierProvider<UserProvider>(
          create: (_) => UserProvider(),
          child: NativeTestHost.app(
              Scaffold(body: NativePrimaryLanguagePicker(homeProvider: home, showSingleLanguageWarning: true)))));
      await NativeTestHost.settle(tester);
      var snapshot = _snapshot(tester, host);
      final toolbar = (snapshot['toolbar'] as List).cast<Map>();
      expect(_ids(toolbar), ['language_close', 'language_save']);
      expect(toolbar.last['enabled'], isFalse, reason: 'nothing chosen yet');
      expect(_ids(_rows(snapshot)), contains('language_single_mode'));
      final first = home.availableLanguages.entries.first;

      await _send(tester, host, 'language_0');
      snapshot = _snapshot(tester, host);
      expect(_rows(snapshot).firstWhere((row) => row['id'] == 'language_0')['symbol'], 'checkmark');
      final viewId = host.created.last;
      await Future.wait([
        host.sendFromNative(viewId, const MethodCall('action', {'id': 'language_save', 'value': null})),
        host.sendFromNative(viewId, const MethodCall('action', {'id': 'language_save', 'value': null})),
      ]);
      await NativeTestHost.settle(tester);
      expect(home.saved, [first.value]);
    });

    testWidgets('search filters the same list and says when nothing matches', (tester) async {
      final host = NativeTestHost.install();
      final home = _Home();
      addTearDown(home.dispose);
      await tester.pumpWidget(NativeTestHost.app(
          Scaffold(body: NativePrimaryLanguagePicker(homeProvider: home, showSingleLanguageWarning: false))));
      await NativeTestHost.settle(tester);
      await host.sendFromNative(host.created.last, const MethodCall('action', {'id': '_search', 'value': 'zzzz'}));
      await NativeTestHost.settle(tester);
      expect(_ids(_rows(_snapshot(tester, host))), ['language_description', 'language_none']);
    });
  });
}

class _Home extends HomeProvider {
  final saved = <String>[];

  @override
  Future<bool> updateUserPrimaryLanguage(String languageCode, {UserProvider? userProvider}) async {
    saved.add(languageCode);
    // A failed save leaves the sheet and every other owner untouched.
    return false;
  }
}

class _Permissions implements OnboardingPermissionsSource {
  final requested = <OnboardingPermission>[];

  @override
  List<OnboardingPermission> get permissions => [OnboardingPermission.location, OnboardingPermission.notifications];

  @override
  Future<OmiPermissionStatus> status(OnboardingPermission permission) async =>
      requested.contains(permission) ? OmiPermissionStatus.granted : OmiPermissionStatus.askable;

  @override
  Future<void> request(OnboardingPermission permission) async => requested.add(permission);
}

class _Analytics implements AnalyticsAdapter {
  final List<String> events = [];
  final List<(String, Map<String, Object>?)> tracked = [];

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    events.add(eventName);
    tracked.add((eventName, properties));
  }

  @override
  void alias({required String newUserId}) {}

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void registerSuperProperties(Map<String, Object> properties) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}
