import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/plugins/plugin_detail.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:url_launcher/url_launcher.dart';

class PluginsPage extends StatefulWidget {
  final bool filterChatOnly;

  const PluginsPage({super.key, this.filterChatOnly = false});

  @override
  _PluginsPageState createState() => _PluginsPageState();
}

class _PluginsPageState extends State<PluginsPage> {
  bool isLoading = true;
  String searchQuery = '';
  List<Plugin> plugins = [];

  Future<void> _fetchPlugins() async {
    var prefs = SharedPreferencesUtil();
    var pluginsList = prefs.pluginsList;
    if (widget.filterChatOnly) {
      pluginsList = pluginsList.where((plugin) => plugin.chat).toList();
    }
    var pluginsId = prefs.pluginsEnabled;
    for (var plugin in pluginsList) {
      plugin.isEnabled = pluginsId.contains(plugin.id);
    }
    plugins = pluginsList.sortedBy((plugin) => plugin.ratingCount * (plugin.ratingAvg ?? 0)).reversed.toList();
    setState(() => isLoading = false);
  }

  @override
  void initState() {
    _fetchPlugins();
    super.initState();
  }

  Future<void> _togglePlugin(String pluginId, bool isEnabled) async {
    var prefs = SharedPreferencesUtil();
    if (isEnabled) {
      prefs.enablePlugin(pluginId);
      MixpanelManager().pluginEnabled(pluginId);
    } else {
      prefs.disablePlugin(pluginId);
      MixpanelManager().pluginDisabled(pluginId);
    }
    _fetchPlugins();
  }

  List<Plugin> _filteredPlugins() {
    return searchQuery.isEmpty
        ? plugins
        : plugins.where((plugin) => plugin.name.toLowerCase().contains(searchQuery.toLowerCase())).toList();
  }

  @override
  Widget build(BuildContext context) {
    final filteredPlugins = _filteredPlugins();
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        automaticallyImplyLeading: true,
        title: const Text('Plugins'),
        centerTitle: true,
        elevation: 0,
        actions: [
          TextButton(
              onPressed: () {
                launchUrl(Uri.parse('https://docs.basedhardware.com/developer/Plugins'));
              },
              child: const Row(
                children: [
                  Text(
                    'Create Yours',
                    style: TextStyle(color: Colors.white),
                  ),
                  SizedBox(
                    width: 8,
                  ),
                ],
              ))
        ],
      ),
      body: GestureDetector(
        onTap: () => FocusScope.of(context).unfocus(),
        child: Column(
          children: [
            const SizedBox(
              height: 32,
            ),
            Container(
              padding: const EdgeInsets.fromLTRB(16, 8, 8, 0),
              margin: const EdgeInsets.fromLTRB(18, 0, 18, 0),
              decoration: const BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.all(Radius.circular(16)),
                border: GradientBoxBorder(
                  gradient: LinearGradient(colors: [
                    Color.fromARGB(127, 208, 208, 208),
                    Color.fromARGB(127, 188, 99, 121),
                    Color.fromARGB(127, 86, 101, 182),
                    Color.fromARGB(127, 126, 190, 236)
                  ]),
                  width: 1,
                ),
                shape: BoxShape.rectangle,
              ),
              // TODO: reuse chat textfield
              child: TextField(
                onChanged: (value) {
                  setState(() {
                    searchQuery = value;
                  });
                },
                obscureText: false,
                decoration: InputDecoration(
                  hintText: 'Find your plugin...',
                  hintStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  suffixIcon: searchQuery.isEmpty
                      ? const SizedBox.shrink()
                      : IconButton(
                          icon: const Icon(
                            Icons.cancel,
                            color: Color(0xFFF7F4F4),
                            size: 28.0,
                          ),
                          onPressed: () {
                            searchQuery = '';
                            setState(() {});
                          },
                        ),
                ),
                style: const TextStyle(
                  // fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                  color: Colors.white,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            Expanded(
              child: ListView.builder(
                itemCount: filteredPlugins.length,
                itemBuilder: (context, index) {
                  final plugin = filteredPlugins[index];
                  return Container(
                    padding: const EdgeInsets.fromLTRB(8, 8, 0, 8),
                    decoration: BoxDecoration(
                      shape: BoxShape.rectangle,
                      borderRadius: const BorderRadius.all(Radius.circular(16.0)),
                      color: Colors.grey.shade900,
                    ),
                    margin: EdgeInsets.only(bottom: 12, top: index == 0 ? 24 : 0, left: 16, right: 16),
                    child: ListTile(
                      onTap: () async {
                        await routeToPage(context, PluginDetailPage(plugin: plugin));
                        _fetchPlugins();
                        // refresh plugins
                      },
                      leading: CircleAvatar(
                        backgroundColor: Colors.white,
                        maxRadius: 28,
                        backgroundImage:
                            NetworkImage('https://raw.githubusercontent.com/BasedHardware/Friend/main/${plugin.image}'),
                      ),
                      title: Text(
                        plugin.name,
                        maxLines: 1,
                        style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.white, fontSize: 16),
                      ),
                      subtitle: Column(
                        mainAxisAlignment: MainAxisAlignment.start,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SizedBox(height: plugin.ratingAvg != null ? 4 : 0),
                          plugin.ratingAvg != null
                              ? Row(
                                  children: [
                                    Text(plugin.getRatingAvg()!),
                                    const SizedBox(width: 4),
                                    const Icon(Icons.star, color: Colors.deepPurple, size: 16),
                                    const SizedBox(width: 4),
                                    Text('(${plugin.ratingCount})'),
                                  ],
                                )
                              : Container(),
                          Padding(
                            padding: const EdgeInsets.only(top: 4.0),
                            child: Text(
                              plugin.description,
                              maxLines: 2,
                              style: const TextStyle(color: Colors.grey, fontSize: 14),
                            ),
                          ),
                        ],
                      ),
                      trailing: IconButton(
                        icon: Icon(
                          plugin.isEnabled ? Icons.check : Icons.arrow_downward_rounded,
                          color: plugin.isEnabled ? Colors.white : Colors.grey,
                        ),
                        onPressed: () {
                          _togglePlugin(plugin.id.toString(), !plugin.isEnabled);
                        },
                      ),
                      // trailing: Switch(
                      //   value: plugin.isEnabled,
                      //   activeColor: Colors.deepPurple,
                      //   onChanged: (value) {
                      //     _togglePlugin(plugin.id.toString(), value);
                      //   },
                      // ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
