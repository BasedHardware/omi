import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/plugins.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';

class PluginProvider extends ChangeNotifier {
  List<Plugin> plugins = [];
  List<Plugin> filteredPlugins = [];

  bool filterChat = true;
  bool filterMemories = true;
  bool filterExternal = true;
  String searchQuery = '';

  List<bool> pluginLoading = [];

  void setPluginLoading(int index, bool value) {
    pluginLoading[index] = value;
    notifyListeners();
  }

  void setChatFilterOnly() {
    filterChat = true;
    filterMemories = false;
    filterExternal = false;
    notifyListeners();
  }

  void setFilterChat(bool value) {
    filterChat = value;
    notifyListeners();
  }

  void setFilterMemories(bool value) {
    filterMemories = value;
    notifyListeners();
  }

  void setFilterExternal(bool value) {
    filterExternal = value;
    notifyListeners();
  }

  void clearSearchQuery() {
    searchQuery = '';
    notifyListeners();
  }

  void filterPlugins(String searchQuery) {
    this.searchQuery = searchQuery;
    var plugins = this
        .plugins
        .where((p) =>
            (p.worksWithChat() && filterChat) ||
            (p.worksWithMemories() && filterMemories) ||
            (p.worksExternally() && filterExternal))
        .toList();

    filteredPlugins = searchQuery.isEmpty
        ? plugins
        : plugins.where((plugin) => plugin.name.toLowerCase().contains(searchQuery.toLowerCase())).toList();
    notifyListeners();
  }

  Future getPlugins() async {
    if (SharedPreferencesUtil().pluginsList.isEmpty) {
      plugins = await retrievePlugins();
    } else {
      plugins = SharedPreferencesUtil().pluginsList;
    }
    filteredPlugins = plugins;
    pluginLoading = List.filled(plugins.length, false);
    notifyListeners();
  }
}
