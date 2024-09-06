import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/plugins.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/home/plugin_temp/plugin_tab_detail_temp.dart';
import 'package:friend_private/pages/home/subscription.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/dialog.dart';

class PluginsTabTempPage extends StatefulWidget {
  final bool filterChatOnly;

  const PluginsTabTempPage({super.key, this.filterChatOnly = false});

  @override
  State<PluginsTabTempPage> createState() => _PluginsTabTempPageState();
}

class _PluginsTabTempPageState extends State<PluginsTabTempPage> {
  bool isLoading = true;
  String searchQuery = '';
  List<Plugin> plugins = SharedPreferencesUtil().pluginsList;
  late List<bool> pluginLoading;

  bool filterChat = true;
  bool filterMemories = true;
  bool filterExternal = true;

  @override
  void initState() {
    if (widget.filterChatOnly) {
      filterChat = true;
      filterMemories = false;
      filterExternal = false;
    }
    pluginLoading = List.filled(plugins.length, false);
    super.initState();
  }

  Future<void> _togglePlugin(String pluginId, bool isEnabled, int idx) async {
    if (pluginLoading[idx]) return;
    setState(() => pluginLoading[idx] = true);
    var prefs = SharedPreferencesUtil();
    if (isEnabled) {
      var enabled = await enablePluginServer(pluginId);
      if (!enabled) {
        showDialog(
            context: context,
            builder: (c) => getDialog(
                  context,
                  () => Navigator.pop(context),
                  () => Navigator.pop(context),
                  'Error activating the plugin',
                  'If this is an integration plugin, make sure the setup is completed.',
                  singleButton: true,
                ));
        setState(() => pluginLoading[idx] = false);
        return;
      }
      prefs.enablePlugin(pluginId);
      MixpanelManager().pluginEnabled(pluginId);
    } else {
      await disablePluginServer(pluginId);
      prefs.disablePlugin(pluginId);
      MixpanelManager().pluginDisabled(pluginId);
    }
    setState(() => pluginLoading[idx] = false);
    setState(() => plugins = SharedPreferencesUtil().pluginsList);
  }

  List<Plugin> _filteredPlugins() {
    var plugins = this
        .plugins
        .where((p) =>
            (p.worksWithChat() && filterChat) ||
            (p.worksWithMemories() && filterMemories) ||
            (p.worksExternally() && filterExternal))
        .toList();

    return searchQuery.isEmpty
        ? plugins
        : plugins
            .where((plugin) =>
                plugin.name.toLowerCase().contains(searchQuery.toLowerCase()))
            .toList();
  }

  @override
  Widget build(BuildContext context) {
    final filteredPlugins = _filteredPlugins();

    filteredPlugins.sort((a, b) {
      int enableComparison =
          b.enabled.toString().compareTo(a.enabled.toString());
      if (enableComparison == 0) {
        int aContentLength = a.content?.length ?? 0;
        int bContentLength = b.content?.length ?? 0;
        return bContentLength.compareTo(aContentLength);
      }
      return enableComparison;
    });

    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      body: ListView.builder(
        shrinkWrap: true,
        padding: const EdgeInsets.only(bottom: 100),
        itemCount: filteredPlugins.length,
        itemBuilder: (context, index) {
          final plugin = filteredPlugins[index];

          debugPrint(
              "filteredPlugins -> ${plugin.name} -> ${plugin.content?.length ?? 0}");
          return GestureDetector(
            onTap: () async {
              //await routeToPage(context, PluginTabDetailPage(plugin: plugin));
              setState(() => plugins = SharedPreferencesUtil().pluginsList);
            },
            child: Container(
              padding: const EdgeInsets.fromLTRB(8, 8, 0, 8),
              decoration: BoxDecoration(
                shape: BoxShape.rectangle,
                borderRadius: const BorderRadius.all(Radius.circular(16.0)),
                color: Colors.grey.shade900,
              ),
              margin: EdgeInsets.only(
                  bottom: 5, top: index == 0 ? 24 : 0, left: 1, right: 1),
              child: Column(
                children: [
                  Row(
                    children: [
                      CachedNetworkImage(
                        imageUrl: plugin.getImageUrl(),
                        imageBuilder: (context, imageProvider) => CircleAvatar(
                          backgroundColor: Colors.white,
                          maxRadius: 18,
                          backgroundImage: imageProvider,
                        ),
                        placeholder: (context, url) =>
                            const CircularProgressIndicator(),
                        errorWidget: (context, url, error) =>
                            const Icon(Icons.error),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              plugin.name,
                              maxLines: 1,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600,
                                  color: Colors.white,
                                  fontSize: 16),
                            ),
                            Text(
                              plugin.description,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  color: Colors.grey, fontSize: 14),
                            ),
                          ],
                        ),
                      ),
                      pluginLoading[index]
                          ? const SizedBox(
                              height: 24,
                              width: 24,
                              child: CircularProgressIndicator(
                                valueColor:
                                    AlwaysStoppedAnimation<Color>(Colors.white),
                              ),
                            )
                          : IconButton(
                              icon: Icon(
                                plugin.enabled
                                    ? Icons.check
                                    : Icons.arrow_downward_rounded,
                                size: 20,
                                color:
                                    plugin.enabled ? Colors.grey : Colors.white,
                              ),
                              onPressed: (!plugin.enabled)
                                  ? () {
                                      if (!plugin.enabled) {
                                        Navigator.of(context).push(
                                            MaterialPageRoute(
                                                builder: (c) =>
                                                    const SubscriptionPage()));
                                      }
                                      /*if (plugin.worksExternally() &&
                                        !plugin.enabled) {
                                      showDialog(
                                        context: context,
                                        builder: (c) => getDialog(
                                          context,
                                          () => Navigator.pop(context),
                                          () async {
                                            Navigator.pop(context);
                                            await routeToPage(
                                                context,
                                                PluginDetailPage(
                                                    plugin: plugin));
                                            setState(() => plugins =
                                                SharedPreferencesUtil()
                                                    .pluginsList);
                                          },
                                          'Authorize External Plugin',
                                          'Do you allow this plugin to access your memories, transcripts, and recordings? Your data will be sent to the plugin\'s server for processing.',
                                          okButtonText: 'Confirm',
                                        ),
                                      );
                                    } else {
                                      _togglePlugin(plugin.id.toString(),
                                          !plugin.enabled, index);
                                    }*/
                                    }
                                  : null,
                            ),
                    ],
                  ),
                  (plugin.content != null &&
                          plugin.content!.isNotEmpty &&
                          plugin.enabled)
                      ? PluginTabDetailTempPage(
                          plugin: plugin,
                          onTap: () async {
                            //await routeToPage(context, PluginTabDetailPage(plugin: plugin));
                            setState(() =>
                                plugins = SharedPreferencesUtil().pluginsList);
                          },
                        )
                      : const SizedBox.shrink(),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
