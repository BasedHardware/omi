import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/add_mcp_server_page.dart';
import 'package:omi/pages/settings/transcription_settings_page.dart';
import 'package:omi/pages/settings/import_history_page.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/user_usage.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/apps/markdown_viewer.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/mobile/native_ui/ios_native_home.dart';
import 'package:omi/mobile/native_ui/ios_native_main_navigation.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'journeys/support/fixture_backend.dart';
import 'visual_audit/screen_frame_fixtures.dart';
import 'visual_audit/fakes.dart';
import 'package:omi/widgets/media_viewer_page.dart';

/// Interactive, seeded Simulator inspection through agent-flutter and native AX.
/// This entry point has no real account, BLE device or production backend.
Future<void> main() async {
  if (!kDebugMode || const String.fromEnvironment('OMI_APP_PROFILE') != 'local_dev') {
    throw StateError('Native inspection requires a local-dev Debug Simulator');
  }
  MarionetteBinding.ensureInitialized();
  final backend = await JourneyFixtureBackend.start();
  SharedPreferences.setMockInitialValues({
    'uid': JourneyFixtureBackend.fixtureUid,
    'email': JourneyFixtureBackend.fixtureEmail,
    'authToken': JourneyFixtureBackend.fixtureBearer,
    'tokenExpirationTime': DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch,
    'appearanceMode': 'dark',
  });
  await SharedPreferencesUtil.init();
  Env.overrideApiBaseUrl(backend.baseUrl);
  PlatformManager.initializeForLocalHarness();
  AuthService.installLocalHarnessTokenGateway(_InspectionGateway());
  await SharedPreferencesUtil().saveCustomSttConfig(
      const CustomSttConfig(provider: SttProvider.openai, apiKey: 'synthetic-only-inspection-key'));
  final usage = UsageProvider(deviceTimeZone: () async => 'Asia/Kolkata');
  usage.debugSetUsage(
      'today',
      UsageStats(
          transcriptionSeconds: 600, speechSeconds: 500, wordsTranscribed: 100, insightsGained: 2, memoriesCreated: 1),
      []);
  runApp(MultiProvider(
      providers: [
        ...defaultAuditProviders(),
        ChangeNotifierProvider(create: (_) => AppearanceProvider()),
        ChangeNotifierProvider<UsageProvider>.value(value: usage)
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        theme: buildOmiTheme(brightness: Brightness.dark),
        home: const _InspectionRoutes(),
      )));
}

class _InspectionRoutes extends StatelessWidget {
  const _InspectionRoutes();
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Synthetic native UI inspection')),
        body: ListView(children: [
          ListTile(
              key: const Key('inspect_main_navigation'),
              title: const Text('Main navigation'),
              onTap: () => Navigator.of(context)
                  .push(MaterialPageRoute<void>(builder: (_) => const _MainNavigationInspection()))),
          ListTile(
              key: const Key('inspect_transcription'),
              title: const Text('Transcription'),
              onTap: () => Navigator.of(context)
                  .push(MaterialPageRoute<void>(builder: (_) => const TranscriptionSettingsPage()))),
          ListTile(
              key: const Key('inspect_import'),
              title: const Text('Import history'),
              onTap: () =>
                  Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const ImportHistoryPage()))),
          ListTile(
              key: const Key('inspect_usage'),
              title: const Text('Plan and usage'),
              onTap: () => Navigator.of(context)
                  .push(MaterialPageRoute<void>(builder: (_) => const UsagePage(debugSkipFetch: true)))),
          ListTile(
              key: const Key('inspect_offline_sync'),
              title: const Text('Offline Sync'),
              onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const AutoSyncPage()))),
          ListTile(
              key: const Key('inspect_mcp'),
              title: const Text('MCP setup'),
              onTap: () =>
                  Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const AddMcpServerPage()))),
          ListTile(
              key: const Key('inspect_media'),
              title: const Text('Synthetic image zoom'),
              onTap: () async {
                final frames = await renderScreenFrameFixtures();
                if (!context.mounted) return;
                await MediaViewerPage.open(context,
                    items: [MediaViewerItem(base64: base64Encode(frames.values.first))]);
              }),
          ListTile(
              key: const Key('inspect_markdown'),
              title: const Text('Setup instructions'),
              onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
                  builder: (_) => const MarkdownViewer(
                        title: 'Setup instructions',
                        markdown:
                            '## Connect your app\n\n1. **Open** [setup](https://example.com/setup).\n2. Keep your account.\n\n> Use the existing service owner.\n\n    {"mode":"native"}',
                      )))),
        ]),
      );
}

class _MainNavigationInspection extends StatelessWidget {
  const _MainNavigationInspection();
  @override
  Widget build(BuildContext context) {
    final home = context.watch<HomeProvider>();
    return Scaffold(
        body: IosNativeMainShell(
      homeIndex: home.selectedIndex,
      navigationRevision: home.navigationRevision,
      onHomeTabSelected: home.setIndex,
      pages: {
        'home': (_) => IosNativeHome(header: const [], footer: [
              NativeHomeAction('chat', 'Ask Omi', 'bubble.left', () {}),
              NativeHomeAction('voice', 'Voice', 'mic', () {}),
              NativeHomeAction('record', 'Record', 'record.circle', () {}),
            ]),
        'tasks': (_) => const ActionItemsPage(),
        'memories': (_) => const MemoriesPage(asRoot: true, showMindMap: false),
        'apps': (_) => const AppsPage(),
        'settings': (_) => const SettingsDrawer(asRoot: true),
      },
    ));
  }
}

class _InspectionGateway implements AuthTokenGateway {
  @override
  AuthUserSnapshot? get currentUser => const AuthUserSnapshot(
      uid: JourneyFixtureBackend.fixtureUid,
      email: JourneyFixtureBackend.fixtureEmail,
      displayName: 'Native inspection');
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => RefreshedAuthToken(
      token: JourneyFixtureBackend.fixtureBearer, expirationTime: DateTime.now().toUtc().add(const Duration(hours: 1)));
  @override
  Future<void> signOut() async {}
}
