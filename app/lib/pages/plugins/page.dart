import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/plugins/list_item.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/plugin_provider.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:provider/provider.dart';

class PluginsPage extends StatefulWidget {
  final bool filterChatOnly;

  const PluginsPage({super.key, this.filterChatOnly = false});

  @override
  State<PluginsPage> createState() => _PluginsPageState();
}

class _PluginsPageState extends State<PluginsPage> with AutomaticKeepAliveClientMixin {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<PluginProvider>().initialize(widget.filterChatOnly);
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        automaticallyImplyLeading: true,
        title: const Text('Plugins'),
        centerTitle: true,
        elevation: 0,
      ),
      body: GestureDetector(
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
                Expanded(
                  child: TabBarView(children: [
                    CustomScrollView(
                      slivers: [
                        const EmptyPluginsWidget(),
                        const SectionTitleWidget(
                          title: 'External Apps',
                          explainer:
                              'When a memory gets created you can use these plugins to send data to external apps like Notion, Zapier, and more.',
                          emoji: '🚀',
                        ),
                        Selector<PluginProvider, List<Plugin>>(
                            selector: (context, provider) =>
                                provider.plugins.where((p) => p.worksExternally()).toList(),
                            builder: (context, memoryIntegrationPlugins, child) {
                              return SliverList(
                                delegate: SliverChildBuilderDelegate(
                                  (context, index) {
                                    return PluginListItem(
                                      plugin: memoryIntegrationPlugins[index],
                                      index: index,
                                    );
                                  },
                                  childCount: memoryIntegrationPlugins.length,
                                ),
                              );
                            }),
                        context.read<PluginProvider>().plugins.isNotEmpty
                            ? SliverToBoxAdapter(child: Divider(color: Colors.grey.shade800, thickness: 1))
                            : const SliverToBoxAdapter(child: SizedBox.shrink()),
                        const SectionTitleWidget(
                          title: 'Prompts',
                          explainer:
                              'When a memory gets created you can use these plugins to extract more information about each memory.',
                          emoji: '📝',
                        ),
                        Selector<PluginProvider, List<Plugin>>(
                            selector: (context, provider) =>
                                provider.plugins.where((p) => p.worksWithMemories()).toList(),
                            builder: (context, memoryPromptPlugins, child) {
                              return SliverList(
                                delegate: SliverChildBuilderDelegate(
                                  (context, index) {
                                    return PluginListItem(
                                      plugin: memoryPromptPlugins[index],
                                      index: index,
                                    );
                                  },
                                  childCount: memoryPromptPlugins.length,
                                ),
                              );
                            }),
                      ],
                    ),
                    CustomScrollView(
                      slivers: [
                        const EmptyPluginsWidget(),
                        const SectionTitleWidget(
                          title: 'Personalities',
                          explainer: 'Personalities for your chat.',
                          emoji: '🤖',
                        ),
                        Selector<PluginProvider, List<Plugin>>(
                            selector: (context, provider) => provider.plugins.where((p) => p.worksWithChat()).toList(),
                            builder: (context, chatPromptPlugins, child) {
                              return SliverList(
                                delegate: SliverChildBuilderDelegate(
                                  (context, index) {
                                    return PluginListItem(
                                      plugin: chatPromptPlugins[index],
                                      index: index,
                                    );
                                  },
                                  childCount: chatPromptPlugins.length,
                                ),
                              );
                            }),
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

class EmptyPluginsWidget extends StatelessWidget {
  const EmptyPluginsWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<PluginProvider>(builder: (context, provider, child) {
      return provider.plugins.isEmpty
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
    return Consumer<PluginProvider>(builder: (context, provider, child) {
      return provider.plugins.isNotEmpty
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