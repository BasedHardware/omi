import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/firebase/model/plugin_model.dart';
import 'package:friend_private/firebase/model/user_memories_model.dart';
import 'package:friend_private/pages/home/plugin_tab_widget.dart';

class PluginsTabPage extends StatefulWidget {
  const PluginsTabPage(
      {required this.userMemoriesModels,
      required this.pluginsModels,
      super.key});

  final List<UserMemoriesModel> userMemoriesModels;
  final List<PluginModel> pluginsModels;

  @override
  State<PluginsTabPage> createState() => _PluginsTabPageState();
}

class _PluginsTabPageState extends State<PluginsTabPage> {
  late List<UserMemoriesModel> plugins;

  @override
  void initState() {
    super.initState();
    plugins = widget.userMemoriesModels
        .where((t) => t.pluginsResults != null && t.pluginsResults!.isNotEmpty)
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    debugPrint("PluginsTabPage -> ${plugins.length}");
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: ListView.separated(
        shrinkWrap: true,
        padding: const EdgeInsets.only(bottom: 100, left: 1, right: 1, top: 10),
        itemCount: plugins.length,
        separatorBuilder: (context, index) {
          final plugin = plugins[index];
          return (plugin.pluginsResults != null &&
                  plugin.pluginsResults!.isNotEmpty)
              ? const Divider(color: Colors.grey)
              : const SizedBox.shrink();
        },
        itemBuilder: (context, index) {
          final plugin = plugins[index];
          return (plugin.pluginsResults != null &&
                  plugin.pluginsResults!.isNotEmpty)
              ? (plugin.pluginsResults != null &&
                      plugin.pluginsResults!.isNotEmpty)
                  ? ListView.separated(
                      shrinkWrap: true,
                      reverse: true,
                      padding: EdgeInsets.zero,
                      itemCount: plugin.pluginsResults!.length,
                      physics: const NeverScrollableScrollPhysics(),
                      separatorBuilder: (context, index) {
                        return const Divider(color: Colors.grey);
                      },
                      itemBuilder: (context, index) {
                        return PluginTabWidget(
                          plugin: plugin,
                          content: plugin.pluginsResults![index],
                          pluginModel: widget.pluginsModels
                              .where((t) =>
                                  t.id ==
                                  plugin.pluginsResults![index].pluginId)
                              .toList()
                              .first,
                          onTap: () async {
                            //await routeToPage(context, PluginTabDetailPage(plugin: plugin));
                            setState(() => plugins =
                                SharedPreferencesUtil().pluginMemoriesList);
                          },
                        );
                      },
                    )
                  : Container()
              : const SizedBox.shrink();
        },
      ),
    );
  }
}
