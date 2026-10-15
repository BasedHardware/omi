import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/found_omi/found_omi_widget.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/onboarding_sync_service.dart';

Widget _host(Widget child) => MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('survey waits for persistence and advances despite failed upload', (tester) async {
    tester.view.physicalSize = const Size(430, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final disk = <String, String>{};
    final persisted = Completer<bool>();
    const session = AuthSessionSnapshot(ownerUid: 'owner', generation: 1);
    final service = OnboardingSyncService(
      read: (owner) => disk[owner] ?? '',
      write: (owner, value) async {
        if (!await persisted.future) return false;
        disk[owner] = value;
        return true;
      },
      send: (_, __) async => false,
      isCurrent: (_) => true,
    )..bindSession(session);
    addTearDown(service.dispose);
    var advanced = 0;
    await tester.pumpWidget(_host(FoundOmiWidget(
      goNext: () => advanced++,
      saveSource: (source) => service.enqueue(session, acquisitionSource: source),
    )));
    await tester.tap(find.text('YouTube'));
    await tester.pump();
    await tester.tap(find.byKey(const Key('found_omi_continue')));
    await tester.pump();
    expect(advanced, 0);
    expect(disk, isEmpty);
    await tester.tap(find.byKey(const Key('found_omi_skip')));
    expect(advanced, 0);
    persisted.complete(true);
    await tester.pump();
    await tester.pump();
    expect(advanced, 1);
    expect(service.pending('owner'), {'acquisition_source': 'YouTube'});
    expect(SharedPreferencesUtil().foundOmiSource, 'YouTube');
    service.dispose();
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('failed local save stays on survey and can be retried', (tester) async {
    tester.view.physicalSize = const Size(430, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var canSave = false;
    var advanced = 0;
    await tester.pumpWidget(_host(FoundOmiWidget(
      goNext: () => advanced++,
      saveSource: (_) async => canSave,
    )));
    await tester.tap(find.text('YouTube'));
    await tester.pump();
    await tester.tap(find.byKey(const Key('found_omi_continue')));
    await tester.pump();
    expect(advanced, 0);
    expect(SharedPreferencesUtil().foundOmiSource, '');
    expect(find.text('Something went wrong! Please try again later.'), findsOneWidget);
    canSave = true;
    await tester.tap(find.byKey(const Key('found_omi_continue')));
    await tester.pump();
    expect(advanced, 1);
  });
}
