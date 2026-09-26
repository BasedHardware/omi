import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';

import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/apps/add_mcp_server_page.dart';
import 'package:omi/pages/apps/explore_install_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class AppsPage extends StatefulWidget {
  final bool showAppBar;
  const AppsPage({super.key, this.showAppBar = false});

  @override
  State<AppsPage> createState() => AppsPageState();
}

class AppsPageState extends State<AppsPage> with AutomaticKeepAliveClientMixin {
  final ScrollController _scrollController = ScrollController();
  final GlobalKey<ExploreInstallPageState> _exploreInstallPageKey = GlobalKey<ExploreInstallPageState>();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_loadApps());
    });
  }

  Future<void> _loadApps() async {
    try {
      final appProvider = context.read<AppProvider>();
      await appProvider.getApps();
      if (mounted) {
        await appProvider.getPopularApps();
      }
    } catch (e, s) {
      Logger.handle(e, s, message: 'Error loading apps page data');
    }
  }

  void scrollToTop() {
    _exploreInstallPageKey.currentState?.scrollToTop();
  }

  /// "+": create an app or add an MCP server.
  Widget _createMenu(BuildContext context) {
    return PullDownButton(
      itemBuilder: (context) => [
        PullDownMenuItem(
          title: context.l10n.createAnApp,
          subtitle: context.l10n.createAndShareYourApp,
          iconWidget: const Icon(Icons.apps, size: 18),
          onTap: () {
            PlatformManager.instance.analytics.pageOpened('Submit App');
            routeToPage(context, const AddAppPage());
          },
        ),
        PullDownMenuItem(
          title: context.l10n.addMcpServer,
          subtitle: context.l10n.connectExternalAiTools,
          iconWidget: const Icon(Icons.cable, size: 18),
          onTap: () {
            PlatformManager.instance.analytics.pageOpened('Add MCP Server');
            routeToPage(context, const AddMcpServerPage());
          },
        ),
      ],
      buttonBuilder: (context, showMenu) => OmiToolbarCapsule(
        children: [
          OmiIconButton(
            icon: const Icon(Icons.add),
            label: context.l10n.createAnApp,
            onPressed: () {
              OmiHaptics.selection();
              showMenu();
            },
          ),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context); // Required for AutomaticKeepAliveClientMixin
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      // Pushed as a page (Settings → Apps): the round back button and "+" to create an app or add
      // an MCP server; the body carries the large "Apps" title.
      appBar: widget.showAppBar ? OmiAppBar(leading: const OmiBackButton(), actions: [_createMenu(context)]) : null,
      body: DefaultTabController(
        length: 1,
        initialIndex: 0,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            // TabBar(
            //   indicatorSize: TabBarIndicatorSize.label,
            //   isScrollable: true,
            //   padding: EdgeInsets.zero,
            //   indicatorPadding: EdgeInsets.zero,
            //   labelStyle: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 18),
            //   indicatorColor: Colors.white,
            //   tabs: const [
            //     Tab(text: 'Explore & Install'),
            //     Tab(text: 'Manage & Create'),
            //   ],
            // ),
            Expanded(
              child: ExploreInstallPage(key: _exploreInstallPageKey, scrollController: _scrollController),
            ),
          ],
        ),
      ),
    );
  }

  @override
  bool get wantKeepAlive => true;
}

class EmptyAppsWidget extends StatelessWidget {
  const EmptyAppsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    // Use Selector to only rebuild when apps list changes, not the entire provider
    return Selector<AppProvider, ({List<App> apps, bool isConnected})>(
      selector: (context, provider) =>
          (apps: provider.apps, isConnected: context.read<ConnectivityProvider>().isConnected),
      builder: (context, state, child) {
        return state.apps.isEmpty
            ? SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.only(top: 64, left: 14, right: 14),
                  child: Center(
                    child: Text(
                      state.isConnected ? context.l10n.noAppsFound : context.l10n.unableToFetchApps,
                      style: OmiType.callout,
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              )
            : const SliverToBoxAdapter(child: SizedBox.shrink());
      },
    );
  }
}
