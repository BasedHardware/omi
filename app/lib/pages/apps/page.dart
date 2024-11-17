import 'package:flutter/material.dart';
import 'package:friend_private/pages/apps/explore_install_page.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:provider/provider.dart';

class AppsPage extends StatefulWidget {
  final bool filterChatOnly;
  const AppsPage({super.key, this.filterChatOnly = false});

  @override
  State<AppsPage> createState() => _AppsPageState();
}

class _AppsPageState extends State<AppsPage> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AddAppProvider>().getCategories();
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: widget.filterChatOnly
          ? AppBar(
              backgroundColor: Theme.of(context).colorScheme.primary,
              automaticallyImplyLeading: true,
              title: const Text('Apps'),
              centerTitle: true,
              elevation: 0,
            )
          : null,
      body: const DefaultTabController(
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
              child: ExploreInstallPage(),
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
}

class EmptyAppsWidget extends StatelessWidget {
  const EmptyAppsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AppProvider>(builder: (context, provider, child) {
      return provider.apps.isEmpty
          ? SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.only(top: 64, left: 14, right: 14),
                child: Center(
                  child: Text(
                    context.read<ConnectivityProvider>().isConnected
                        ? 'No apps found'
                        : 'Unable to fetch apps :(\n\nPlease check your internet connection and try again.',
                    style: const TextStyle(color: Colors.white, fontSize: 16),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            )
          : const SliverToBoxAdapter(child: SizedBox.shrink());
    });
  }
}
