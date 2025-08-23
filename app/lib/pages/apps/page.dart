import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/explore_install_page.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:provider/provider.dart';

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
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AddAppProvider>().getCategories();
    });
    super.initState();
  }

  void scrollToTop() {
    _exploreInstallPageKey.currentState?.scrollToTop();
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
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: widget.showAppBar
          ? AppBar(
              backgroundColor: Theme.of(context).colorScheme.primary,
              automaticallyImplyLeading: true,
              title: const Text('Apps'),
              centerTitle: true,
              elevation: 0,
            )
          : null,
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
              child: ExploreInstallPage(
                key: _exploreInstallPageKey,
                scrollController: _scrollController,
              ),
            ),
            // const Expanded(
            //     child: TabBarView(
            //   children: [
            //     ExploreInstallPage(),
            //     ManageCreatePage(),
            //   ],
            // )),
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
      selector: (context, provider) => (
        apps: provider.apps,
        isConnected: context.read<ConnectivityProvider>().isConnected,
      ),
      builder: (context, state, child) {
        return state.apps.isEmpty
            ? SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.only(top: 64, left: 14, right: 14),
                  child: Center(
                    child: Text(
                      state.isConnected ? 'No apps found' : 'Unable to fetch apps :(\n\nPlease check your internet connection and try again.',
                      style: const TextStyle(color: Colors.white, fontSize: 16),
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
