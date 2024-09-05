import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/firebase/model/user_memories_model.dart';
import 'package:friend_private/pages/home/plugin_tab_detail.dart';
import 'package:friend_private/pages/home/plugin_tab_widget.dart';
import 'package:friend_private/utils/other/temp.dart';

class PluginsTabPage extends StatefulWidget {
  const PluginsTabPage({super.key});

  @override
  State<PluginsTabPage> createState() => _PluginsTabPageState();
}

class _PluginsTabPageState extends State<PluginsTabPage> {
  List<UserMemoriesModel> plugins = SharedPreferencesUtil()
      .pluginMemoriesList
      .where((t) => t.pluginsResults != null && t.pluginsResults!.isNotEmpty)
      .toList();

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
              ? (plugin.pluginsResults != null && plugin.pluginsResults!.isNotEmpty)
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
                          onTap: () async {
                            //await routeToPage(context, PluginTabDetailPage(plugin: plugin));
                            setState(() =>
                                plugins = SharedPreferencesUtil().pluginMemoriesList);
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
