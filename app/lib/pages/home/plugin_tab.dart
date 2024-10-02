import 'package:flutter/material.dart';
import 'package:friend_private/firebase/model/plugin_model.dart';
import 'package:friend_private/firebase/model/user_memories_model.dart';
import 'package:friend_private/pages/home/plugin_tab_detail.dart';
import 'package:friend_private/pages/home/plugin_tab_widget.dart';
import 'package:friend_private/utils/other/temp.dart';

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
        .where((t) =>
            t.pluginsResults != null &&
            t.pluginsResults!.isNotEmpty &&
            t.deleted == false)
        .toList();

    plugins.sort((b, a) => (a.createdAt ?? DateTime(2023, 1, 1))
        .compareTo(b.createdAt ?? DateTime(2023, 1, 1)));
  }

  @override
  Widget build(BuildContext context) {
    debugPrint("cc -> ${plugins.length}");
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: ListView.builder(
        shrinkWrap: true,
        padding: const EdgeInsets.only(bottom: 100, top: 10, left: 0, right: 0),
        itemCount: plugins.length,
        itemBuilder: (context, ind) {
          final plugin = plugins[ind];
          return (plugin.pluginsResults != null &&
                  plugin.pluginsResults!.isNotEmpty)
              ? (plugin.pluginsResults != null &&
                      plugin.pluginsResults!.isNotEmpty)
                  ? ListView.builder(
                      shrinkWrap: true,
                      reverse: true,
                      padding: EdgeInsets.zero,
                      itemCount: plugin.pluginsResults!.length,
                      physics: const NeverScrollableScrollPhysics(),
                      itemBuilder: (context, index) {
                        return PluginTabWidget(
                          isDividerShow: true,
                          isInstallButtonShow: false,
                          userMemoriesModel: plugin,
                          pluginsResult: plugin.pluginsResults![index],
                          pluginModel: widget.pluginsModels
                              .where((t) =>
                                  t.id ==
                                  plugin.pluginsResults![index].pluginId)
                              .toList()
                              .first,
                          onTap: () async {
                            await routeToPage(
                                context,
                                PluginTabDetailPage(
                                  userMemoriesModel: plugin,
                                  pluginModel: widget.pluginsModels
                                      .where((t) =>
                                          t.id ==
                                          plugin
                                              .pluginsResults![index].pluginId)
                                      .toList()
                                      .first,
                                  userMemoriesModels: plugins,
                                  pluginsModels: widget.pluginsModels,
                                ));
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
