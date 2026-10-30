/// An announcement is marked seen only on an explicit answer — its call to action or its close X —
/// never on a stray scrim tap; "Not Now" postpones (docs/ux-contract.md §14).
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/announcement.dart';
import 'package:omi/pages/announcements/announcement_dialog.dart';

Announcement _announcement() => Announcement.fromJson({
      'id': 'a-1',
      'type': 'announcement',
      'created_at': '2026-09-01T00:00:00Z',
      'active': true,
      'content': {'title': 'Meet Omi Memories', 'body': 'Everything you said, remembered.'},
    });

void main() {
  late AnnouncementOutcome? outcome;

  Future<void> open(WidgetTester tester) async {
    outcome = null;
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () async => outcome = await AnnouncementDialog.show(context, _announcement()),
                child: const Text('show'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('show'));
    await tester.pumpAndSettle();
  }

  testWidgets('a tap on the scrim does not dismiss it', (tester) async {
    await open(tester);
    await tester.tapAt(const Offset(5, 5));
    await tester.pumpAndSettle();
    expect(find.text('Meet Omi Memories'), findsOneWidget);
    expect(outcome, isNull);
  });

  testWidgets('the close X is an answer that marks it seen', (tester) async {
    await open(tester);
    await tester.tap(find.byTooltip('Close'));
    await tester.pumpAndSettle();
    expect(outcome, AnnouncementOutcome.closed);
    expect(outcome!.marksSeen, isTrue);
  });

  testWidgets('Not Now postpones: it is not marked seen', (tester) async {
    await open(tester);
    expect(find.text('Maybe Later'), findsNothing);
    await tester.tap(find.text('Not Now'));
    await tester.pumpAndSettle();
    expect(outcome, AnnouncementOutcome.notNow);
    expect(outcome!.marksSeen, isFalse);
  });

  test('leaving without an answer does not mark it seen', () {
    expect(AnnouncementOutcome.none.marksSeen, isFalse);
    expect(AnnouncementOutcome.cta.marksSeen, isTrue);
  });

  group('call to action', () {
    test('navigate: opens an in-app route, as the backend model documents', () {
      final action = AnnouncementAction.parse('navigate:/memories');
      expect(action, isA<AnnouncementRoute>());
      expect((action! as AnnouncementRoute).route, '/memories');
      expect(
        (AnnouncementAction.parse('navigate:settings/data-privacy')! as AnnouncementRoute).route,
        '/settings/data-privacy',
      );
      expect((AnnouncementAction.parse('/apps/abc')! as AnnouncementRoute).route, '/apps/abc');
    });

    test('url: and bare web links open externally; anything else is ignored', () {
      expect(
        (AnnouncementAction.parse('url:https://omi.me/blog')! as AnnouncementUrl).uri.toString(),
        'https://omi.me/blog',
      );
      expect((AnnouncementAction.parse('https://omi.me')! as AnnouncementUrl).uri.host, 'omi.me');
      expect(AnnouncementAction.parse('navigate:'), isNull);
      expect(AnnouncementAction.parse('memories'), isNull);
    });

    test('only http(s) links with a host are opened', () {
      expect(AnnouncementAction.parse('url:tel:12345'), isNull);
      expect(AnnouncementAction.parse('url:file:///sdcard/secret.txt'), isNull);
      expect(AnnouncementAction.parse('url:someapp://open'), isNull);
      expect(AnnouncementAction.parse('url:https:'), isNull);
      expect(AnnouncementAction.parse('http://omi.me'), isA<AnnouncementUrl>());
    });
  });
}
