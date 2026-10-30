// Apps before the UI program: the store, filters, app detail, submitting and managing an app, MCP
// servers and the AI app generator. The standalone data-access consent helper did not exist yet.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/apps/add_mcp_server_page.dart';
import 'package:omi/pages/apps/app_detail/app_detail.dart';
import 'package:omi/pages/apps/page.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/update_app.dart';
import 'package:omi/pages/apps/widgets/filter_sheet.dart';
import 'package:omi/pages/settings/ai_app_generator_page.dart';
import 'package:omi/providers/app_provider.dart';

import '../../../../journeys/support/fixture_backend.dart';
import '../fakes.dart';
import '../../../harness.dart';

App _app({required String id, String name = 'Asana', String? uid, bool externalIntegration = false}) {
  return App(
    id: id,
    uid: uid,
    name: name,
    author: 'Omi',
    description: 'Sync your tasks with $name.',
    image: 'https://example.invalid/$id.png',
    capabilities: {if (externalIntegration) 'external_integration', 'chat'},
    status: 'approved',
    category: 'productivity',
    approved: true,
    ratingCount: 12,
    ratingAvg: 4.5,
    enabled: false,
    deleted: false,
    isPaid: false,
    isUserPaid: false,
  );
}

/// An AppProvider whose catalog is [apps] under one "Popular" section, with nothing enabled.
AppProvider _catalog(List<App> apps) => AppProvider()
  ..retrieveAppsGroupedOverride = (() async => [
        {'title': 'Popular', 'data': apps},
      ])
  ..getEnabledAppsOverride = (() async => const [])
  ..retrievePopularAppsOverride = (() async => apps);

final appsScenarios = <AuditScenario>[
  AuditScenario(
    id: 'apps-store',
    title: 'Apps store home',
    page: 'lib/pages/apps/page.dart (AppsPage)',
    state: 'AppProvider catalog with two approved apps under Popular; none enabled',
    run: (a) async {
      final apps = [_app(id: 'asana'), _app(id: 'notion', name: 'Notion')];
      await primeNetworkImages(a.tester, apps.map((app) => app.getImageUrl()));
      await a.pump(const AppsPage(showAppBar: true), providers: [
        ChangeNotifierProvider<AppProvider>.value(value: _catalog(apps)),
        ChangeNotifierProvider<AddAppProvider>(create: (_) => InertAddAppProvider()),
      ]);
      await a.shot('Open the Apps tab');
    },
  ),
  AuditScenario(
    id: 'apps-filter-sheet',
    title: 'Apps filter sheet',
    page: 'lib/pages/apps/widgets/filter_sheet.dart (FilterBottomSheet)',
    state: 'AppProvider catalog with one approved app',
    run: (a) async {
      // As lib/pages/apps/explore_install_page.dart opened it at this revision.
      await a.pumpHost(
          (context) => showModalBottomSheet(
                context: context,
                isScrollControlled: true,
                shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
                builder: (_) => const FilterBottomSheet(),
              ),
          providers: [
            ChangeNotifierProvider<AppProvider>.value(value: _catalog([_app(id: 'asana')]))
          ]);
      await a.shot('Open the Apps filter sheet');
    },
  ),
  AuditScenario(
    id: 'apps-detail',
    title: 'App detail page',
    page: 'lib/pages/apps/app_detail/app_detail.dart (AppDetailPage)',
    state: 'An approved, not-enabled app with an external integration',
    run: (a) async {
      final app = _app(id: 'asana', externalIntegration: true);
      await primeNetworkImages(a.tester, [app.getImageUrl()]);
      await a.pump(AppDetailPage(app: app), providers: [
        ChangeNotifierProvider<AppProvider>.value(value: _catalog([app])),
        ChangeNotifierProvider<AddAppProvider>(create: (_) => InertAddAppProvider()),
      ]);
      await a.shot('Open an app detail page');
    },
  ),
  AuditScenario(
    id: 'apps-submit',
    title: 'Submit App form',
    page: 'lib/pages/apps/add_app.dart (AddAppPage)',
    state: 'AddAppProvider with one category and no capabilities or payment plans loaded',
    run: (a) async {
      await a.pump(const AddAppPage(), providers: [
        ChangeNotifierProvider<AddAppProvider>(create: (_) => InertAddAppProvider()),
      ]);
      await a.shot('Open the Submit App form');
    },
  ),
  AuditScenario(
    id: 'apps-manage',
    title: 'Manage an app the reader owns',
    page: 'lib/pages/apps/update_app.dart (UpdateAppPage)',
    state: 'An approved app whose uid is the signed-in fixture account',
    run: (a) async {
      final owned = _app(id: 'my-app', name: 'My Own App', uid: JourneyFixtureBackend.fixtureUid);
      await primeNetworkImages(a.tester, [owned.image, owned.getImageUrl()]);
      await a.pump(UpdateAppPage(app: owned), providers: [
        ChangeNotifierProvider<AddAppProvider>(create: (_) => InertAddAppProvider()),
      ]);
      await a.shot('Open Manage App for an owned app');
    },
  ),
  AuditScenario(
    id: 'apps-add-mcp-server',
    title: 'Add MCP Server',
    page: 'lib/pages/apps/add_mcp_server_page.dart (AddMcpServerPage)',
    state: 'Signed-in fixture account; the form is not submitted',
    run: (a) async {
      await a.pump(const AddMcpServerPage());
      await a.shot('Open Add MCP Server');
    },
  ),
  AuditScenario(
    id: 'apps-ai-generator',
    title: 'AI app generator prompt',
    page: 'lib/pages/settings/ai_app_generator_page.dart (AiAppGeneratorPage)',
    state: 'Empty AppProvider catalog',
    run: (a) async {
      await a.pump(const AiAppGeneratorPage(), providers: [
        ChangeNotifierProvider<AppProvider>.value(value: _catalog([])),
      ]);
      await a.shot('Open the AI app generator prompt step');
    },
  ),
];
