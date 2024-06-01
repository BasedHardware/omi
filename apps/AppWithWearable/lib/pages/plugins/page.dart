import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/plugin.dart';

import 'package:friend_private/flutter_flow/flutter_flow_theme.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';
import 'package:google_fonts/google_fonts.dart';
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
    var plugins = SharedPreferencesUtil().pluginsList;
    var pluginsId = SharedPreferencesUtil().pluginsEnabled;
    for (var plugin in plugins) {
      plugin.isEnabled = pluginsId.contains(plugin.id);
    }
    this.plugins = plugins;
    setState(() => isLoading = false);
  }

  @override
  void initState() {
    _fetchPlugins();
    super.initState();
  }

  Future<void> _togglePlugin(String pluginId, bool isEnabled) async {
    // FOR NOW ENABLE SINGLE PLUGIN
    if (isEnabled) {
      SharedPreferencesUtil().pluginsEnabled = [pluginId];
      for (var p in plugins) {
        p.isEnabled = p.id == pluginId;
      }
    } else {
      SharedPreferencesUtil().pluginsEnabled = [];
      for (var p in plugins) {
        p.isEnabled = false;
      }
    }
    setState(() {});
  }

  List<Plugin> _filteredPlugins() {
    if (searchQuery.isEmpty) {
      return plugins;
    }
    return plugins.where((plugin) => plugin.name.toString().toLowerCase().contains(searchQuery.toLowerCase())).toList();
  }

  @override
  Widget build(BuildContext context) {
    final filteredPlugins = _filteredPlugins();
    final unFocusNode = FocusNode();
    return GestureDetector(
      onTap: () => unFocusNode.canRequestFocus
          ? FocusScope.of(context).requestFocus(unFocusNode)
          : FocusScope.of(context).unfocus(),
      child: Scaffold(
        appBar: AppBar(
          backgroundColor: FlutterFlowTheme.of(context).primaryColor,
          automaticallyImplyLeading: true,
          title: const Text('Plugins'),
          centerTitle: false,
          elevation: 2.0,
          actions: [
            TextButton(
                onPressed: () {
                  launchUrl(Uri.parse('https://github.com/BasedHardware/Friend/blob/main/plugins-instruction.md'));
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
                    // Icon(
                    //   Icons.build,
                    //   color: Colors.white,
                    // ),
                  ],
                ))
          ],
        ),
        body: Stack(
          children: [
            const BlurBotWidget(),
            Column(
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
                  child: TextField(
                    onChanged: (value) {
                      setState(() {
                        searchQuery = value;
                      });
                    },
                    obscureText: false,
                    decoration: InputDecoration(
                      hintText: 'Search your plugin',
                      hintStyle: FlutterFlowTheme.of(context).bodySmall.override(
                            fontFamily: FlutterFlowTheme.of(context).bodySmallFamily,
                            color: FlutterFlowTheme.of(context).primaryText,
                            fontSize: 14.0,
                            fontWeight: FontWeight.w500,
                            useGoogleFonts:
                                GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodySmallFamily),
                          ),
                      enabledBorder: const UnderlineInputBorder(
                        borderSide: BorderSide(
                          color: Color(0x00000000),
                          width: 1.0,
                        ),
                        borderRadius: BorderRadius.only(
                          topLeft: Radius.circular(4.0),
                          topRight: Radius.circular(4.0),
                        ),
                      ),
                      focusedBorder: const UnderlineInputBorder(
                        borderSide: BorderSide(
                          color: Color(0x00000000),
                          width: 1.0,
                        ),
                        borderRadius: BorderRadius.only(
                          topLeft: Radius.circular(4.0),
                          topRight: Radius.circular(4.0),
                        ),
                      ),
                      errorBorder: const UnderlineInputBorder(
                        borderSide: BorderSide(
                          color: Color(0x00000000),
                          width: 1.0,
                        ),
                        borderRadius: BorderRadius.only(
                          topLeft: Radius.circular(4.0),
                          topRight: Radius.circular(4.0),
                        ),
                      ),
                      focusedErrorBorder: const UnderlineInputBorder(
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
                    style: FlutterFlowTheme.of(context).bodyMedium.override(
                          fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                          color: FlutterFlowTheme.of(context).primaryText,
                          fontWeight: FontWeight.w500,
                          useGoogleFonts:
                              GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                        ),
                  ),
                ),
                ListView.builder(
                  itemCount: filteredPlugins.length,
                  scrollDirection: Axis.vertical,
                  shrinkWrap: true,
                  itemBuilder: (context, index) {
                    if (index < 0 || index >= filteredPlugins.length) return null;
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
              ],
            ),
          ],
        ),
      ),
    );
  }
}
