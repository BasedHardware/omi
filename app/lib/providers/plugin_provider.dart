import 'package:friend_private/backend/http/api/plugins.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/utils/alerts/app_dialog.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class PluginProvider extends BaseProvider {
  List<Plugin> plugins = [];

  bool filterChat = true;
  bool filterMemories = true;
  bool filterExternal = true;
  String searchQuery = '';

  List<bool> pluginLoading = [];

  void setPluginLoading(int index, bool value) {
    pluginLoading[index] = value;
    notifyListeners();
  }

  void clearSearchQuery() {
    searchQuery = '';
    notifyListeners();
  }

  Future getPlugins() async {
    setLoadingState(true);
    plugins = await retrievePlugins();
    updatePrefPlugins();
    setPlugins();
    setLoadingState(false);
    notifyListeners();
  }

  void updatePrefPlugins() {
    SharedPreferencesUtil().pluginsList = plugins;
  }

  void setPlugins() {
    plugins = SharedPreferencesUtil().pluginsList;
    notifyListeners();
  }

  void initialize(bool filterChatOnly) {
    if (filterChatOnly) {
      filterChat = true;
      filterMemories = false;
      filterExternal = false;
    }
    pluginLoading = List.filled(plugins.length, false);

    getPlugins();
    notifyListeners();
  }

  Future<void> togglePlugin(String pluginId, bool isEnabled, int idx) async {
    if (pluginLoading[idx]) return;
    pluginLoading[idx] = true;
    notifyListeners();
    var prefs = SharedPreferencesUtil();
    if (isEnabled) {
      var enabled = await enablePluginServer(pluginId);
      if (!enabled) {
        AppDialog.show(
          title: 'Error activating the plugin',
          content: 'If this is an integration plugin, make sure the setup is completed.',
          singleButton: true,
        );

        pluginLoading[idx] = false;
        notifyListeners();

        return;
      }
      prefs.enablePlugin(pluginId);
      MixpanelManager().pluginEnabled(pluginId);
    } else {
      await disablePluginServer(pluginId);
      prefs.disablePlugin(pluginId);
      MixpanelManager().pluginDisabled(pluginId);
    }
    pluginLoading[idx] = false;
    plugins = SharedPreferencesUtil().pluginsList;
    notifyListeners();
  }

  List<Plugin> get filteredPlugins {
    var pluginList = plugins
        .where((p) =>
            (p.worksWithChat() && filterChat) ||
            (p.worksWithMemories() && filterMemories) ||
            (p.worksExternally() && filterExternal))
        .toList();

    return searchQuery.isEmpty
        ? pluginList
        : pluginList.where((plugin) => plugin.name.toLowerCase().contains(searchQuery.toLowerCase())).toList();
  }

  void updateSearchQuery(String query) {
    searchQuery = query;
    notifyListeners();
  }

  void toggleFilterChat() {
    filterChat = !filterChat;
    notifyListeners();
  }

  void toggleFilterMemories() {
    filterMemories = !filterMemories;
    notifyListeners();
  }

  void toggleFilterExternal() {
    filterExternal = !filterExternal;
    notifyListeners();
  }
}
