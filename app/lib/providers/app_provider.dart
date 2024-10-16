import 'package:collection/collection.dart';
import 'package:friend_private/backend/http/api/plugins.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/utils/alerts/app_dialog.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class AppProvider extends BaseProvider {
  List<App> apps = [];

  bool filterChat = true;
  bool filterMemories = true;
  bool filterExternal = true;
  String searchQuery = '';

  List<bool> appLoading = [];

  String selectedChatAppId = 'no_selected';

  void setSelectedChatAppId(String? appId) {
    if (appId == null) {
      selectedChatAppId = SharedPreferencesUtil().selectedChatAppId;
    } else {
      selectedChatAppId = appId;
      SharedPreferencesUtil().selectedChatAppId = appId;
    }
    notifyListeners();
  }

  App? getSelectedPlugin() {
    return apps.firstWhereOrNull((p) => p.id == selectedChatAppId);
  }

  void setAppLoading(int index, bool value) {
    appLoading[index] = value;
    notifyListeners();
  }

  void clearSearchQuery() {
    searchQuery = '';
    notifyListeners();
  }

  Future getApps() async {
    setLoadingState(true);
    apps = await retrieveApps();
    updatePrefApps();
    setApps();
    setLoadingState(false);
    notifyListeners();
  }

  void setAppsFromCache() {
    if (SharedPreferencesUtil().appsList.isNotEmpty) {
      apps = SharedPreferencesUtil().appsList;
    }
    notifyListeners();
  }

  void updatePrefApps() {
    SharedPreferencesUtil().appsList = apps;
  }

  void setApps() {
    apps = SharedPreferencesUtil().appsList;
    notifyListeners();
  }

  void initialize(bool filterChatOnly) {
    if (filterChatOnly) {
      filterChat = true;
      filterMemories = false;
      filterExternal = false;
    }
    appLoading = List.filled(apps.length, false);

    getApps();
    notifyListeners();
  }

  Future<void> togglePlugin(String pluginId, bool isEnabled, int idx) async {
    if (appLoading[idx]) return;
    appLoading[idx] = true;
    notifyListeners();
    var prefs = SharedPreferencesUtil();
    if (isEnabled) {
      var enabled = await enableAppServer(pluginId);
      if (!enabled) {
        AppDialog.show(
          title: 'Error activating the plugin',
          content: 'If this is an integration plugin, make sure the setup is completed.',
          singleButton: true,
        );

        appLoading[idx] = false;
        notifyListeners();

        return;
      }
      prefs.enableApp(pluginId);
      MixpanelManager().pluginEnabled(pluginId);
    } else {
      await disableAppServer(pluginId);
      prefs.disableApp(pluginId);
      MixpanelManager().pluginDisabled(pluginId);
    }
    appLoading[idx] = false;
    apps = SharedPreferencesUtil().appsList;
    notifyListeners();
  }

  // List<Plugin> get filteredPlugins {
  //   var pluginList = plugins
  //       .where((p) =>
  //           (p.worksWithChat() && filterChat) ||
  //           (p.worksWithMemories() && filterMemories) ||
  //           (p.worksExternally() && filterExternal))
  //       .toList();
  //
  //   return searchQuery.isEmpty
  //       ? pluginList
  //       : pluginList.where((plugin) => plugin.name.toLowerCase().contains(searchQuery.toLowerCase())).toList();
  // }

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
