// IMG_1157: "Teach Omi your voice" is a new account's first To do, drawn like a task, while the
// voice profile is missing; it is gone once the profile exists (it was a card over Conversations).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/action_items/widgets/task_row_parts.dart';
import 'package:omi/pages/action_items/widgets/voice_setup_task.dart';
import 'package:omi/providers/home_provider.dart';

void main() {
  final en = lookupAppLocalizations(const Locale('en'));

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  Future<HomeProvider> pump(WidgetTester tester, {required bool hasVoice}) async {
    final home = HomeProvider()..hasSpeakerProfile = hasVoice;
    addTearDown(home.dispose);
    await tester.pumpWidget(ChangeNotifierProvider<HomeProvider>.value(
      value: home,
      child: const MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: [Locale('en')],
        home: Scaffold(body: VoiceSetupTask()),
      ),
    ));
    return home;
  }

  testWidgets('without a voice profile it is a task: an open ring, the title and why', (tester) async {
    await pump(tester, hasVoice: false);
    expect(find.text(en.teachOmiYourVoice), findsOneWidget);
    expect(find.text(en.voiceSetupTaskSubline), findsOneWidget);
    expect(find.byType(TaskCompletionMark), findsOneWidget);
    expect(find.bySemanticsLabel('${en.teachOmiYourVoice}, ${en.voiceSetupTaskSubline}'), findsOneWidget);
  });

  testWidgets('with a voice profile there is nothing to do', (tester) async {
    await pump(tester, hasVoice: true);
    expect(find.text(en.teachOmiYourVoice), findsNothing);
  });

  testWidgets('it leaves the moment the profile is made', (tester) async {
    final home = await pump(tester, hasVoice: false);
    home.setSpeakerProfile(true);
    await tester.pump();
    expect(find.text(en.teachOmiYourVoice), findsNothing);
  });
}
