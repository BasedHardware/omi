import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/http/api/google_calendars.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/google_calendar_selection_page.dart';
import 'package:omi/services/integrations/google_calendar_service.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const calendars = [
  ReadableGoogleCalendar('primary-id', 'Personal', true, true),
  ReadableGoogleCalendar('team-id', 'Team', false, true),
  ReadableGoogleCalendar('removed-id', '', false, false),
];

typedef Request = Future<GoogleCalendarSelection> Function(String owner, {GoogleCalendarSelection? selection});

Future<void> open(WidgetTester tester, Request request) async {
  await tester.pumpWidget(MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: const [Locale('en')],
    home: Builder(
        builder: (context) => Scaffold(
                body: TextButton(
              child: const Text('Open'),
              onPressed: () => Navigator.of(context).push(MaterialPageRoute<void>(
                builder: (_) => GoogleCalendarSelectionPage(request: request),
              )),
            ))),
  ));
  await tester.tap(find.text('Open'));
  await tester.pumpAndSettle();
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'calendar-owner'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    GoogleCalendarService.invalidateMeetings();
  });

  testWidgets('primary defaults, multiple selection, write destination and Save', (tester) async {
    GoogleCalendarSelection? saved;
    await open(tester, (owner, {selection}) async {
      saved ??= selection;
      return selection ?? const GoogleCalendarSelection('primary-id', calendars, {'primary-id'});
    });
    expect(find.text('Read selected calendars. New events use Personal.'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('calendar-team-id')));
    expect(saved, isNull, reason: 'Selection is only a local draft before Save');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(saved!.selectedIds, {'primary-id', 'team-id'});
    expect(find.text('Open'), findsOneWidget);
  });

  testWidgets('Back cancels the local draft without an API mutation', (tester) async {
    var writes = 0;
    await open(tester, (owner, {selection}) async {
      if (selection != null) writes++;
      return const GoogleCalendarSelection('primary-id', calendars, {'primary-id'});
    });
    await tester.tap(find.byKey(const ValueKey('calendar-team-id')));
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(writes, 0);
  });

  testWidgets('an unavailable selection can be removed and primary can be excluded', (tester) async {
    GoogleCalendarSelection? saved;
    await open(tester, (owner, {selection}) async {
      saved = selection;
      return selection ?? const GoogleCalendarSelection('primary-id', calendars, {'removed-id'});
    });
    expect(find.textContaining('No longer available'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('calendar-removed-id')));
    await tester.pump();
    await tester.tap(find.text('Save'));
    await tester.pump();
    expect(saved, isNull, reason: 'At least one calendar must be selected');
    await tester.tap(find.byKey(const ValueKey('calendar-team-id')));
    await tester.pump();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(saved!.selectedIds, {'team-id'});
  });

  testWidgets('a refused save preserves the draft and supports retry', (tester) async {
    var refuse = true;
    await open(tester, (owner, {selection}) async {
      if (selection != null && refuse) throw StateError('refused');
      return selection ?? const GoogleCalendarSelection('primary-id', calendars, {'primary-id'});
    });
    await tester.tap(find.byKey(const ValueKey('calendar-team-id')));
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(find.text('Calendar settings'), findsOneWidget);
    refuse = false;
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(find.text('Open'), findsOneWidget);
  });

  testWidgets('an old account picker never submits into a replacement session', (tester) async {
    var writes = 0;
    await open(tester, (owner, {selection}) async {
      if (selection != null) writes++;
      return const GoogleCalendarSelection('primary-id', calendars, {'primary-id'});
    });
    SharedPreferencesUtil().uid = 'replacement-owner';
    await tester.tap(find.text('Save'));
    await tester.pump();
    expect(writes, 0);
  });

  testWidgets('lost calendar access hides protected rows instead of displaying stale choices', (tester) async {
    await open(tester, (owner, {selection}) async {
      if (selection != null) {
        throw const GoogleCalendarSelectionFailure(ApiProblem(ApiProblemKind.forbidden));
      }
      return const GoogleCalendarSelection('primary-id', calendars, {'primary-id'});
    });
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(find.text('Personal'), findsNothing);
    expect(find.text('Team'), findsNothing);
    expect(find.text('Refresh'), findsOneWidget);
  });

  testWidgets('repeated Save during a pending request is single flight', (tester) async {
    final pending = Completer<GoogleCalendarSelection>();
    var writes = 0;
    await open(tester, (owner, {selection}) async {
      if (selection == null) return const GoogleCalendarSelection('primary-id', calendars, {'primary-id'});
      writes++;
      return pending.future;
    });
    await tester.tap(find.text('Save'));
    await tester.pump();
    await tester.tap(find.text('Save'), warnIfMissed: false);
    await tester.pump();
    expect(writes, 1);
    pending.complete(const GoogleCalendarSelection('primary-id', calendars, {'primary-id'}));
    await tester.pumpAndSettle();
  });
}
