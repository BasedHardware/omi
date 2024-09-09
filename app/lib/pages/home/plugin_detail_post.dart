import 'package:flutter/material.dart';
import 'package:friend_private/firebase/model/plugin_model.dart';
import 'package:friend_private/firebase/model/user_memories_model.dart';
import 'package:friend_private/pages/home/plugin_tab_widget.dart';

class PluginDetailPostPage extends StatefulWidget {
  final PluginModel pluginModel;
  final List<UserMemoriesModel> userMemoriesModels;
  final List<PluginModel> pluginsModels;

  const PluginDetailPostPage({
    super.key,
    required this.pluginModel,
    required this.userMemoriesModels,
    required this.pluginsModels,
  });

  @override
  State<PluginDetailPostPage> createState() => _PluginDetailPostPageState();
}

class _PluginDetailPostPageState extends State<PluginDetailPostPage> {
  late List<UserMemoriesModel> plugins;

  @override
  void initState() {
    super.initState();
    plugins = widget.userMemoriesModels
        .where((t) =>
            t.pluginsResults != null &&
            t.pluginsResults!.isNotEmpty &&
            t.deleted == false &&
            t.pluginsResults!
                .where((p) => p.pluginId == widget.pluginModel.id)
                .toList()
                .isNotEmpty)
        .toList();

    plugins.sort((b, a) => (a.createdAt ?? DateTime(2023, 1, 1))
        .compareTo(b.createdAt ?? DateTime(2023, 1, 1)));
  }

  @override
  Widget build(BuildContext context) {
    debugPrint("PluginsTabPage -> ${plugins.length}");
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: ListView.builder(
        shrinkWrap: true,
        padding: const EdgeInsets.only(bottom: 20, top: 10),
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
                        PluginModel pluginModelTemp = widget.pluginsModels
                            .where((t) =>
                                t.id == plugin.pluginsResults![index].pluginId)
                            .toList()
                            .first;

                        if (pluginModelTemp.id == widget.pluginModel.id) {
                          return PluginTabWidget(
                            isDividerShow: true,
                            isInstallButtonShow: false,
                            userMemoriesModel: plugin,
                            pluginsResult: plugin.pluginsResults![index],
                            pluginModel: pluginModelTemp,
                            onTap: () async {
                              /*await routeToPage(
                                  context,
                                  PluginTabDetailPage(
                                    userMemoriesModel: plugin,
                                    pluginModel: widget.pluginsModels
                                        .where((t) =>
                                            t.id ==
                                            plugin.pluginsResults![index]
                                                .pluginId)
                                        .toList()
                                        .first,
                                    userMemoriesModels: plugins,
                                    pluginsModels: widget.pluginsModels,
                                  ));*/
                            },
                          );
                        } else {
                          return Container();
                        }
                      },
                    )
                  : Container()
              : const SizedBox.shrink();
        },
      ),
    );
  }
}
