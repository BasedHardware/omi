import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/add_app.dart';
import 'package:friend_private/pages/apps/list_item.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';

class ManageCreatePage extends StatelessWidget {
  const ManageCreatePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AppProvider>(builder: (context, provider, child) {
      return CustomScrollView(
        slivers: [
          const SliverToBoxAdapter(child: SizedBox(height: 18)),
          SliverToBoxAdapter(
            child: Row(
              children: [
                const SizedBox(width: 16),
                ChoiceChip(
                  label: const Text('Installed Apps'),
                  selected: provider.installedAppsOptionSelected,
                  showCheckmark: true,
                  backgroundColor: Colors.transparent,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                  onSelected: (bool selected) {
                    provider.updateInstalledAppsOptionSelected(true);
                  },
                ),
                const SizedBox(width: 10),
                ChoiceChip(
                  label: const Text('My Apps'),
                  selected: !provider.installedAppsOptionSelected,
                  showCheckmark: true,
                  backgroundColor: Colors.transparent,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                  onSelected: (bool selected) {
                    provider.updateInstalledAppsOptionSelected(false);
                  },
                ),
              ],
            ),
          ),
          SliverToBoxAdapter(
            child: AnimatedSwitcher(
              transitionBuilder: (child, animation) => FadeTransition(
                opacity: animation,
                child: child,
              ),
              duration: const Duration(milliseconds: 500),
              child: provider.installedAppsOptionSelected
                  ? Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 16),
                        Padding(
                          padding: const EdgeInsets.only(left: 16.0),
                          child: Text('Apps (${provider.apps.where((a) => a.enabled).length})',
                              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w400)),
                        ),
                        Selector<AppProvider, List<App>>(
                          selector: (context, provider) => provider.apps.where((p) => p.enabled).toList(),
                          builder: (context, memoryPromptApps, child) {
                            return ListView.builder(
                              itemCount: memoryPromptApps.length,
                              physics: const NeverScrollableScrollPhysics(),
                              shrinkWrap: true,
                              itemBuilder: (context, index) {
                                return AppListItem(
                                  app: memoryPromptApps[index],
                                  index: index,
                                );
                              },
                            );
                          },
                        ),
                        const SizedBox(
                          height: 50,
                        ),
                      ],
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const SizedBox(height: 16),
                        GestureDetector(
                          onTap: () {
                            MixpanelManager().pageOpened('Submit App');
                            routeToPage(context, const AddAppPage());
                          },
                          child: Container(
                            padding: const EdgeInsets.all(12.0),
                            margin: const EdgeInsets.only(left: 12.0, right: 12.0, top: 2, bottom: 24),
                            decoration: BoxDecoration(
                              color: Colors.grey.shade900,
                              borderRadius: BorderRadius.circular(16.0),
                            ),
                            child: const ListTile(
                              title: Row(
                                crossAxisAlignment: CrossAxisAlignment.center,
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(Icons.add, color: Colors.white),
                                  SizedBox(width: 8),
                                  Text(
                                    'Create and submit a new app',
                                    textAlign: TextAlign.center,
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                        provider.userPrivateApps.isEmpty
                            ? const SizedBox()
                            : Padding(
                                padding: const EdgeInsets.only(left: 16.0, bottom: 10),
                                child: Text('Private Apps (${provider.userPrivateApps.length})',
                                    style: const TextStyle(fontSize: 18)),
                              ),
                        provider.userPrivateApps.isEmpty
                            ? const SizedBox()
                            : ListView.builder(
                                itemCount: provider.userPrivateApps.length,
                                shrinkWrap: true,
                                itemBuilder: (context, index) {
                                  return AppListItem(
                                    showPrivateIcon: false,
                                    app: provider.userPrivateApps[index],
                                    index: provider.apps.indexOf(provider.userPrivateApps[index]),
                                  );
                                },
                              ),
                        provider.userPublicApps.isEmpty
                            ? const SizedBox()
                            : Padding(
                                padding: const EdgeInsets.only(left: 16.0, bottom: 10),
                                child: Text('Public Apps (${provider.userPublicApps.length})',
                                    style: const TextStyle(fontSize: 18)),
                              ),
                        provider.userPublicApps.isEmpty
                            ? const SizedBox()
                            : ListView.builder(
                                itemCount: provider.userPublicApps.length,
                                shrinkWrap: true,
                                itemBuilder: (context, index) {
                                  return AppListItem(
                                    app: provider.userPublicApps[index],
                                    index: provider.apps.indexOf(provider.userPublicApps[index]),
                                  );
                                },
                              ),
                      ],
                    ),
            ),
          ),
        ],
      );
    });
  }
}
