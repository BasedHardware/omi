import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/developer_mode_provider.dart';

/// Regression guards for #11365: saving Developer Settings used to re-enable
/// every webhook whose URL field was non-empty (the backend enables on set),
/// and it reported success without awaiting the requests.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late DeveloperModeProvider provider;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    provider = DeveloperModeProvider();
  });

  tearDown(() {
    provider.dispose();
  });

  Future<void> pumpHost(WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: const Scaffold(body: SizedBox.shrink()),
      ),
    );
  }

  testWidgets('a save does not re-enable webhooks the user toggled off', (tester) async {
    await pumpHost(tester);
    final setTypes = <String>[];
    final disabledTypes = <String>[];
    provider.setUserWebhookUrlOverride = ({required String type, required String url}) async {
      setTypes.add(type);
      return true;
    };
    provider.disableWebhookOverride = ({required String type}) async => disabledTypes.add(type);

    provider.webhookOnConversationCreated.text = 'https://example.com/memory';
    provider.webhookOnTranscriptReceived.text = 'https://example.com/ingest';
    provider.conversationEventsToggled = true;
    // Off with a URL still in the field, plus audio bytes off with no URL —
    // the ",5" payload the audio-bytes save builds is non-empty either way.
    provider.transcriptsToggled = false;
    provider.audioBytesToggled = false;
    provider.daySummaryToggled = false;

    provider.saveSettings();
    await tester.pumpAndSettle();

    expect(setTypes, containsAll(['audio_bytes', 'realtime_transcript', 'memory_created', 'day_summary']));
    expect(disabledTypes, containsAll(['audio_bytes', 'realtime_transcript', 'day_summary']));
    expect(disabledTypes, isNot(contains('memory_created')));
    expect(SharedPreferencesUtil().webhookOnTranscriptReceived, 'https://example.com/ingest');
  });

  testWidgets('a rejected save surfaces an error and does not persist the URLs', (tester) async {
    await pumpHost(tester);
    provider.setUserWebhookUrlOverride =
        ({required String type, required String url}) async => type != 'memory_created';
    provider.disableWebhookOverride = ({required String type}) async {};

    provider.webhookOnConversationCreated.text = 'https://example.com/memory';
    provider.conversationEventsToggled = true;

    provider.saveSettings();
    await tester.pump();
    await tester.pump();

    expect(SharedPreferencesUtil().webhookOnConversationCreated, '');
    expect(find.text('Failed to save. Please check your connection.'), findsOneWidget);
    expect(find.text('Settings saved!'), findsNothing);
    expect(provider.savingSettingsLoading, isFalse);

    await tester.pumpAndSettle();
  });
}
