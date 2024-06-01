import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';

class PluginsPage extends StatefulWidget {
  const PluginsPage({Key? key}) : super(key: key);

  @override
  _PluginsPageState createState() => _PluginsPageState();
}

class _PluginsPageState extends State<PluginsPage> {
  late SharedPreferences prefs;
  late http.Client httpClient;
  bool isLoading = true;
  String searchQuery = '';

  @override
  void initState() {
    super.initState();
    httpClient = http.Client();
    _initPrefs();
  }

  Future<void> _initPrefs() async {
    prefs = await SharedPreferences.getInstance();
    await _fetchPlugins();
  }

  Future<void> _fetchPlugins() async {
    setState(() => isLoading = true);
    final response = await httpClient.get(Uri.parse('https://raw.githubusercontent.com/BasedHardware/Friend/main/community-plugins.json'));
    if (response.statusCode == 200) {
      final List<dynamic> fetchedPlugins = json.decode(response.body) as List<dynamic>;
      final List<dynamic> storedPlugins = _getStoredPluginData();
      final Set<String> fetchedPluginIds = fetchedPlugins.map((plugin) => plugin['id'].toString()).toSet();
      final List<dynamic> updatedPlugins = fetchedPlugins.map((plugin) {
        final existingPlugin = storedPlugins.firstWhere((storedPlugin) => storedPlugin['id'] == plugin['id'], orElse: () => {});
        final isEnabled = existingPlugin.isNotEmpty ? existingPlugin['isEnabled'] : false;
        return {...plugin, 'isEnabled': isEnabled};
      }).toList();
      await prefs.setString('plugins', json.encode(updatedPlugins));
      setState(() => isLoading = false);
    } else {
      setState(() => isLoading = false);
    }
  }

  Future<void> _togglePlugin(String pluginId, bool isEnabled) async {
    final List<dynamic> storedPlugins = _getStoredPluginData();
    if (isEnabled) {
      for (var plugin in storedPlugins) {
        plugin['isEnabled'] = false;
      }
    }
    final int pluginIndex = storedPlugins.indexWhere((plugin) => plugin['id'].toString() == pluginId);
    if (pluginIndex != -1) {
      storedPlugins[pluginIndex]['isEnabled'] = true;
      await prefs.setString('plugins', json.encode(storedPlugins));
      setState(() {});
    }
  }

  @override
  void dispose() {
    httpClient.close();
    super.dispose();
  }

  List<dynamic> _getStoredPluginData() {
    final String? storedPluginsString = prefs.getString('plugins');
    if (storedPluginsString != null) {
      return json.decode(storedPluginsString) as List<dynamic>;
    }
    return [];
  }

  List<dynamic> _filteredPlugins() {
    final plugins = _getStoredPluginData();
    if (searchQuery.isEmpty) {
      return plugins;
    } else {
      return plugins.where((plugin) => plugin['name'].toString().toLowerCase().contains(searchQuery.toLowerCase())).toList();
    }
  }

  @override
  Widget build(BuildContext context) {
    final filteredPlugins = _filteredPlugins();
    return Scaffold(
      appBar: AppBar(
        backgroundColor: FlutterFlowTheme.of(context).primaryColor,
        automaticallyImplyLeading: true,
        title: const Text('Plugins'),
        centerTitle: false,
        elevation: 2.0,
      ),
      body: Column(
        children: [
          Container(
            color: Colors.white,
            padding: const EdgeInsets.all(8.0),
            child: TextField(
              style: const TextStyle(color: Colors.black),
              decoration: InputDecoration(
                filled: true,
                fillColor: Colors.black12,
                labelText: 'Search Plugins',
                labelStyle: const TextStyle(color: Colors.black),
                hintText: 'Enter a search term',
                hintStyle: const TextStyle(color: Colors.black54),
                border: OutlineInputBorder(borderSide: BorderSide(color: Colors.black)),
                enabledBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.black)),
                focusedBorder: OutlineInputBorder(borderSide: BorderSide(color: Colors.white)),
                suffixIcon: const Icon(Icons.search, color: Colors.black),
              ),
              onChanged: (value) => setState(() => searchQuery = value),
            ),
          ),
          Expanded(
            child: Stack(
              children: [
                const BlurBotWidget(),
                if (isLoading)
                  const Center(child: CircularProgressIndicator())
                else if (filteredPlugins.isNotEmpty)
                  ListWheelScrollView.useDelegate(
                    perspective: 0.0015,
                    itemExtent: 200,
                    physics: const FixedExtentScrollPhysics(),
                    childDelegate: ListWheelChildBuilderDelegate(
                      builder: (BuildContext context, int index) {
                        if (index < 0 || index >= filteredPlugins.length) return null;
                        final plugin = filteredPlugins[index];
                        final isEnabled = plugin['isEnabled'] as bool? ?? false;
                        return Card(
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(20.0),
                          ),
                          color: Colors.black,
                          margin: const EdgeInsets.all(10),
                          child: Container(
                            width: 350,
                            padding: const EdgeInsets.all(16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  plugin['name'] ?? 'Unnamed Plugin',
                                  style: const TextStyle(
                                    fontSize: 20,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                                const SizedBox(height: 10),
                                Text(
                                  'By ${plugin['author'] ?? 'Unknown'}',
                                  style: const TextStyle(
                                    fontSize: 16,
                                    color: Colors.white70,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                                const SizedBox(height: 10),
                                Expanded(
                                  child: Text(
                                    plugin['description'] ?? 'No description provided.',
                                    style: const TextStyle(
                                      fontSize: 14,
                                      color: Colors.white60,
                                    ),
                                    overflow: TextOverflow.ellipsis,
                                    maxLines: 3,
                                  ),
                                ),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    Switch(
                                      value: isEnabled,
                                      onChanged: (value) {
                                        _togglePlugin(plugin['id'].toString(), value);
                                      },
                                      activeTrackColor: Colors.greenAccent,
                                      activeColor: Colors.green,
                                      inactiveTrackColor: Colors.white30,
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                      childCount: filteredPlugins.length,
                    ),
                  )
                else
                  const Center(
                    child: Text(
                      'No plugins available',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
