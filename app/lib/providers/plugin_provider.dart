import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/plugins.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';

class PluginProvider extends ChangeNotifier {
  List<Plugin> plugins = [];

  Future getPlugins() async {
    if (SharedPreferencesUtil().pluginsList.isEmpty) {
      plugins = await retrievePlugins();
    } else {
      plugins = SharedPreferencesUtil().pluginsList;
    }
    notifyListeners();
  }
}
