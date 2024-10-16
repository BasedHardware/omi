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

class _PluginsPageState extends State<PluginsPage> {
  @override
  void initState() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<PluginProvider>().initialize(widget.filterChatOnly);
    });
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PluginProvider>(builder: (context, provider, child) {
      List<Plugin> memoryPromptPlugins = provider.plugins.where((p) => p.worksWithMemories()).toList();
      List<Plugin> memoryIntegrationPlugins = provider.plugins.where((p) => p.worksExternally()).toList();
      List<Plugin> chatPromptPlugins = provider.plugins.where((p) => p.worksWithChat()).toList();

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
                          _emptyPluginsWidget(provider),
                          _getSectionTitle(
                            context,
                            provider,
                            'External Apps',
                            '🚀',
                            'When a memory gets created you can use these plugins to send data to external apps like Notion, Zapier, and more.',
                          ),
                          SliverList(
                            delegate: SliverChildBuilderDelegate(
                              (context, index) {
                                return PluginListItem(
                                  plugin: memoryIntegrationPlugins[index],
                                  index: index,
                                  provider: provider,
                                );
                              },
                              childCount: memoryIntegrationPlugins.length,
                            ),
                          ),
                          provider.plugins.isNotEmpty
                              ? SliverToBoxAdapter(child: Divider(color: Colors.grey.shade800, thickness: 1))
                              : const SliverToBoxAdapter(child: SizedBox.shrink()),
                          _getSectionTitle(context, provider, 'Prompts', '📝',
                              'When a memory gets created you can use these plugins to extract more information about each memory.'),
                          SliverList(
                            delegate: SliverChildBuilderDelegate(
                              (context, index) {
                                return PluginListItem(
                                  plugin: memoryPromptPlugins[index],
                                  index: index,
                                  provider: provider,
                                );
                              },
                              childCount: memoryPromptPlugins.length,
                            ),
                          ),
                        ],
                      ),
                      CustomScrollView(
                        slivers: [
                          _emptyPluginsWidget(provider),
                          _getSectionTitle(context, provider, 'Personalities', '🤖', 'Personalities for your chat.'),
                          SliverList(
                            delegate: SliverChildBuilderDelegate(
                              (context, index) {
                                return PluginListItem(
                                  plugin: chatPromptPlugins[index],
                                  index: index,
                                  provider: provider,
                                );
                              },
                              childCount: chatPromptPlugins.length,
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
    });
  }

  _getSectionTitle(BuildContext context, PluginProvider provider, String title, String emoji, String explainer) {
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
  }

  _emptyPluginsWidget(provider) {
    return provider.plugins.isEmpty
        ? SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.only(top: 64, left: 14, right: 14),
              child: Center(
                child: Text(
                  context.read<ConnectivityProvider>().isConnected
                      ? 'No plugins found'
                      : 'Unable to fetch plugins :(\n\nPlease check your internet connection and try again.',
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          )
        : const SliverToBoxAdapter(child: SizedBox.shrink());
  }
}
