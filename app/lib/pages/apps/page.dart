import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/add_app.dart';
import 'package:friend_private/pages/apps/list_item.dart';
import 'package:friend_private/pages/apps/providers/add_app_provider.dart';
import 'package:friend_private/pages/chat/widgets/animated_mini_banner.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/dialog.dart';
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
      appBar: null,
      body: DefaultTabController(
        length: 2,
        initialIndex: 0,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                TabBar(
                  indicatorSize: TabBarIndicatorSize.label,
                  isScrollable: true,
                  padding: EdgeInsets.zero,
                  indicatorPadding: EdgeInsets.zero,
                  labelStyle: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 18),
                  indicatorColor: Colors.white,
                  tabs: const [
                    Tab(text: 'Explore & Install'),
                    Tab(text: 'Manage & Create'),
                  ],
                ),
                const Spacer(),
                const Icon(
                  Icons.search,
                  color: Colors.white,
                ),
                const SizedBox(
                  width: 12,
                ),
              ],
            ),
            Expanded(
                child: TabBarView(
              children: [
                // For You
                CustomScrollView(
                  slivers: [
                    const SliverToBoxAdapter(child: SizedBox(height: 18)),
                    SliverToBoxAdapter(
                      child: SizedBox(
                        height: 40,
                        child: Selector<AddAppProvider, List<Category>>(
                          selector: (ctx, provider) => provider.categories,
                          builder: (ctx, categories, child) {
                            return ListView.separated(
                                scrollDirection: Axis.horizontal,
                                itemBuilder: (ctx, idx) {
                                  if (idx == 0) {
                                    return Padding(
                                      padding: const EdgeInsets.only(left: 8.0),
                                      child: ChoiceChip(
                                        label: const Row(
                                          children: [
                                            Icon(
                                              Icons.filter_list_alt,
                                              size: 15,
                                            ),
                                            SizedBox(width: 4),
                                            Text('Filter'),
                                          ],
                                        ),
                                        selected: false,
                                        showCheckmark: true,
                                        backgroundColor: Colors.transparent,
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(8),
                                        ),
                                        onSelected: (bool selected) {},
                                      ),
                                    );
                                  }
                                  return ChoiceChip(
                                    label: Text(categories[idx].title),
                                    selected: false,
                                    showCheckmark: true,
                                    backgroundColor: Colors.transparent,
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    onSelected: (bool selected) {},
                                  );
                                },
                                separatorBuilder: (ctx, idx) {
                                  return const SizedBox(
                                    width: 10,
                                  );
                                },
                                itemCount: categories.length + 1);
                          },
                        ),
                      ),
                    ),
                    Selector<AppProvider, List<App>>(
                      selector: (context, provider) => provider.apps.where((p) => p.worksExternally()).toList(),
                      builder: (context, memoryIntegrationApps, child) {
                        return SliverList(
                          delegate: SliverChildBuilderDelegate(
                            (context, index) {
                              return AppListItem(
                                app: memoryIntegrationApps[index],
                                index: index,
                              );
                            },
                            childCount: memoryIntegrationApps.length,
                          ),
                        );
                      },
                    ),
                  ],
                ),
                // Memories
                Selector<AppProvider, List<App>>(
                  selector: (context, provider) => provider.apps.where((p) => p.worksWithMemories()).toList(),
                  builder: (context, memoryPromptApps, child) {
                    return ListView.separated(
                      shrinkWrap: true,
                      itemBuilder: (ctx, index) {
                        return AppListItem(
                          app: memoryPromptApps[index],
                          index: index,
                        );
                      },
                      separatorBuilder: (ctx, index) {
                        return const SizedBox();
                      },
                      itemCount: memoryPromptApps.length,
                    );
                  },
                ),
              ],
            )),
          ],
        ),
      ),
    );
  }
}

class AppsPage2 extends StatefulWidget {
  final bool filterChatOnly;

  const AppsPage2({super.key, this.filterChatOnly = false});

  @override
  State<AppsPage2> createState() => _AppsPage2State();
}

class _AppsPage2State extends State<AppsPage2> with AutomaticKeepAliveClientMixin {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AppProvider>().initialize(widget.filterChatOnly);
      context.read<AddAppProvider>().getAppCapabilities();
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
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
      body: context.read<AppProvider>().loading
          ? const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ),
                  SizedBox(
                    height: 14,
                  ),
                  Text(
                    'Loading apps',
                    style: TextStyle(color: Colors.white),
                  ),
                ],
              ),
            )
          : GestureDetector(
              onTap: () => FocusScope.of(context).unfocus(),
              child: DefaultTabController(
                  length: 2,
                  initialIndex: widget.filterChatOnly ? 1 : 0,
                  child: Column(
                    children: [
                      TabBar(
                        indicatorSize: TabBarIndicatorSize.label,
                        isScrollable: false,
                        padding: EdgeInsets.zero,
                        indicatorPadding: EdgeInsets.zero,
                        labelStyle: Theme.of(context).textTheme.titleLarge!.copyWith(fontSize: 18),
                        indicatorColor: Colors.transparent,
                        tabs: const [Tab(text: 'Memories'), Tab(text: 'Chat')],
                      ),
                      InkWell(
                        onTap: () {
                          MixpanelManager().pageOpened('Submit App');
                          routeToPage(context, const AddAppPage());
                        },
                        child: AnimatedMiniBanner(
                            showAppBar: true,
                            height: 10,
                            child: Container(
                              color: Colors.grey[800],
                              child: const Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Text('Create your own app', style: TextStyle(color: Colors.white, fontSize: 16)),
                                ],
                              ),
                            )),
                      ),
                      Expanded(
                        child: TabBarView(children: [
                          CustomScrollView(
                            slivers: [
                              const EmptyAppsWidget(),
                              const SectionTitleWidget(
                                title: 'External Apps',
                                explainer:
                                    'When a memory gets created you can use these apps to send data to external apps like Notion, Zapier, and more.',
                                emoji: '🚀',
                              ),
                              Selector<AppProvider, List<App>>(
                                  selector: (context, provider) =>
                                      provider.apps.where((p) => p.worksExternally()).toList(),
                                  builder: (context, memoryIntegrationApps, child) {
                                    return SliverList(
                                      delegate: SliverChildBuilderDelegate(
                                        (context, index) {
                                          return AppListItem(
                                            app: memoryIntegrationApps[index],
                                            index: index,
                                          );
                                        },
                                        childCount: memoryIntegrationApps.length,
                                      ),
                                    );
                                  }),
                              context.read<AppProvider>().apps.isNotEmpty
                                  ? SliverToBoxAdapter(child: Divider(color: Colors.grey.shade800, thickness: 1))
                                  : const SliverToBoxAdapter(child: SizedBox.shrink()),
                              const SectionTitleWidget(
                                title: 'Prompts',
                                explainer:
                                    'When a memory gets created you can use these apps to extract more information about each memory.',
                                emoji: '📝',
                              ),
                              Selector<AppProvider, List<App>>(
                                  selector: (context, provider) =>
                                      provider.apps.where((p) => p.worksWithMemories()).toList(),
                                  builder: (context, memoryPromptApps, child) {
                                    return SliverList(
                                      delegate: SliverChildBuilderDelegate(
                                        (context, index) {
                                          return AppListItem(
                                            app: memoryPromptApps[index],
                                            index: index,
                                          );
                                        },
                                        childCount: memoryPromptApps.length,
                                      ),
                                    );
                                  }),
                              const SliverToBoxAdapter(
                                child: SizedBox(
                                  height: 120,
                                ),
                              ),
                            ],
                          ),
                          CustomScrollView(
                            slivers: [
                              const EmptyAppsWidget(),
                              const SectionTitleWidget(
                                title: 'Personalities',
                                explainer: 'Personalities for your chat.',
                                emoji: '🤖',
                              ),
                              Selector<AppProvider, List<App>>(
                                  selector: (context, provider) =>
                                      provider.apps.where((p) => p.worksWithChat()).toList(),
                                  builder: (context, chatPromptApps, child) {
                                    return SliverList(
                                      delegate: SliverChildBuilderDelegate(
                                        (context, index) {
                                          return AppListItem(
                                            app: chatPromptApps[index],
                                            index: index,
                                          );
                                        },
                                        childCount: chatPromptApps.length,
                                      ),
                                    );
                                  }),
                              const SliverToBoxAdapter(
                                child: SizedBox(
                                  height: 120,
                                ),
                              ),
                            ],
                          ),
                        ]),
                      )
                    ],
                  )),
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

class SectionTitleWidget extends StatelessWidget {
  final String title;
  final String emoji;
  final String explainer;
  const SectionTitleWidget({super.key, required this.title, required this.emoji, required this.explainer});

  @override
  Widget build(BuildContext context) {
    return Consumer<AppProvider>(builder: (context, provider, child) {
      return provider.apps.isNotEmpty
          ? SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.only(top: 32),
                child: GestureDetector(
                  onTap: () {
                    showDialog(
                      context: context,
                      builder: (c) => getDialog(
                        context,
                        () => Navigator.pop(context),
                        () => Navigator.pop(context),
                        '$title $emoji',
                        explainer,
                        singleButton: true,
                        okButtonText: 'Got it!',
                      ),
                    );
                  },
                  child: Center(
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(title, style: const TextStyle(color: Colors.white, fontSize: 18)),
                        const SizedBox(width: 12),
                        Text(emoji, style: const TextStyle(fontSize: 18)),
                      ],
                    ),
                  ),
                ),
              ),
            )
          : const SliverToBoxAdapter(child: SizedBox.shrink());
    });
  }
}
