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
import 'package:omi/pages/apps/markdown_viewer.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'journeys/support/fixture_backend.dart';
import 'visual_audit/screen_frame_fixtures.dart';
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
  runApp(ChangeNotifierProvider(
      create: (_) => AppearanceProvider(),
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
