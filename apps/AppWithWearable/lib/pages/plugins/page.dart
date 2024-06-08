import 'package:flutter/material.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/plugin.dart';

import 'package:friend_private/widgets/blur_bot_widget.dart';
import 'package:url_launcher/url_launcher.dart';

class PluginsPage extends StatefulWidget {
  const PluginsPage({Key? key}) : super(key: key);

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
    var pluginsId = prefs.pluginsEnabled;
    for (var plugin in pluginsList) {
      plugin.isEnabled = pluginsId.contains(plugin.id);
    }
    plugins = pluginsList;
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
    } else {
      prefs.disablePlugin(pluginId);
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
      appBar: AppBar(
        backgroundColor: Theme.of(context).primaryColor,
        automaticallyImplyLeading: true,
        title: const Text('Plugins'),
        centerTitle: false,
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
      body: Column(
        children: [
          const SizedBox(
            height: 32,
          ),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            margin: const EdgeInsets.symmetric(horizontal: 16),
            decoration: BoxDecoration(
              color: const Color(0x1AF7F4F4),
              boxShadow: const [
                BoxShadow(
                  blurRadius: 3.0,
                  color: Color(0x33000000),
                  offset: Offset(0.0, 1.0),
                )
              ],
              borderRadius: BorderRadius.circular(12.0),
            ),
            // TODO: reuse chat textfield
            child: TextField(
              onChanged: (value) {
                setState(() {
                  searchQuery = value;
                });
              },
              obscureText: false,
              decoration: const InputDecoration(
                hintText: 'Search your plugin',
                hintStyle: TextStyle(
                  color: Colors.white,
                  fontSize: 14.0,
                  fontWeight: FontWeight.w500,
                ),
                enabledBorder: UnderlineInputBorder(
                  borderSide: BorderSide(
                    color: Color(0x00000000),
                    width: 1.0,
                  ),
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(4.0),
                    topRight: Radius.circular(4.0),
                  ),
                ),
                focusedBorder: UnderlineInputBorder(
                  borderSide: BorderSide(
                    color: Color(0x00000000),
                    width: 1.0,
                  ),
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(4.0),
                    topRight: Radius.circular(4.0),
                  ),
                ),
                errorBorder: UnderlineInputBorder(
                  borderSide: BorderSide(
                    color: Color(0x00000000),
                    width: 1.0,
                  ),
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(4.0),
                    topRight: Radius.circular(4.0),
                  ),
                ),
                focusedErrorBorder: UnderlineInputBorder(
                  borderSide: BorderSide(
                    color: Color(0x00000000),
                    width: 1.0,
                  ),
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(4.0),
                    topRight: Radius.circular(4.0),
                  ),
                ),
              ),
              style: TextStyle(
                // fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                color: Theme.of(context).primaryColor,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          Expanded(
            child: ListView.builder(
              itemCount: filteredPlugins.length,
              itemBuilder: (context, index) {
                final plugin = filteredPlugins[index];
                return Padding(
                  padding: const EdgeInsets.only(top: 16, left: 10, right: 10),
                  child: ListTile(
                    title: Text(
                      plugin.name,
                      style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.white, fontSize: 16),
                    ),
                    subtitle: Padding(
                      padding: const EdgeInsets.only(top: 4.0),
                      child: Text(
                        plugin.description,
                        style: const TextStyle(color: Colors.grey, fontSize: 14),
                      ),
                    ),
                    trailing: Switch(
                      value: plugin.isEnabled,
                      activeColor: Colors.deepPurple,
                      onChanged: (value) {
                        _togglePlugin(plugin.id.toString(), value);
                      },
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
