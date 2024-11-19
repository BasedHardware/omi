import 'package:collection/collection.dart';
import 'package:friend_private/backend/http/api/apps.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/utils/alerts/app_dialog.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class AppProvider extends BaseProvider {
  List<App> apps = [];

  bool filterChat = true;
  bool filterMemories = true;
  bool filterExternal = true;
  String searchQuery = '';
  bool installedAppsOptionSelected = true;

  List<bool> appLoading = [];

  String selectedChatAppId = 'no_selected';

  bool isAppOwner = false;
  bool appPublicToggled = false;

  bool isLoading = false;

  List<Category> categories = [];
  List<AppCapability> capabilities = [];
  Map<String, dynamic> filters = {};
  List<App> filteredApps = [];

  List<App> get userPrivateApps => apps.where((app) => app.private).toList();

  List<App> get userPublicApps =>
      apps.where((app) => (!app.private && app.uid == SharedPreferencesUtil().uid)).toList();

  void updateInstalledAppsOptionSelected(bool value) {
    installedAppsOptionSelected = value;
    notifyListeners();
  }

  void addOrRemoveFilter(String filter, String filterGroup) {
    if (filters.containsKey(filterGroup)) {
      filters[filterGroup] = filter;
    } else {
      filters.addAll({filterGroup: filter});
    }
    notifyListeners();
  }

  void addOrRemoveCategoryFilter(Category category) {
    if (filters.containsKey('Category')) {
      filters['Category'] = category;
    } else {
      filters.addAll({'Category': category});
    }
    notifyListeners();
  }

  void addOrRemoveCapabilityFilter(AppCapability capability) {
    if (filters.containsKey('Capabilities')) {
      filters['Capabilities'] = capability;
    } else {
      filters.addAll({'Capabilities': capability});
    }
    notifyListeners();
  }

  bool isFilterSelected(String filter, String filterGroup) {
    return filters.containsKey(filterGroup) && filters[filterGroup] == filter;
  }

  bool isCategoryFilterSelected(Category category) {
    return filters.containsKey('Category') && filters['Category'] == category;
  }

  bool isCapabilityFilterSelected(AppCapability capability) {
    return filters.containsKey('Capabilities') && filters['Capabilities'] == capability;
  }

  void clearFilters() {
    filters.clear();
    notifyListeners();
  }

  void removeFilter(String filterGroup) {
    filters.remove(filterGroup);
    notifyListeners();
  }

  bool isFilterActive() {
    return filters.isNotEmpty;
  }

  bool isSearchActive() {
    return searchQuery.isNotEmpty;
  }

  void searchApps(String query) {
    if (query.isEmpty) {
      filteredApps = apps;
      searchQuery = '';
    } else {
      searchQuery = query;
      filteredApps = apps.where((app) => app.name.toLowerCase().contains(query.toLowerCase())).toList();
    }
    notifyListeners();
  }

  void filterApps() {
    if (!isFilterActive()) {
      filteredApps = apps;
      return;
    }
    filteredApps = apps;
    filters.forEach((key, value) {
      switch (key) {
        case 'Apps':
          if (value == 'Installed Apps') {
            filteredApps = filteredApps.where((app) => app.enabled).toList();
          } else if (value == 'My Apps') {
            filteredApps = filteredApps.where((app) => app.isOwner(SharedPreferencesUtil().uid)).toList();
          }
          break;
        case 'Sort':
          if (value == 'A-Z') {
            filteredApps.sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
          } else if (value == 'Z-A') {
            filteredApps.sort((a, b) => b.name.toLowerCase().compareTo(a.name.toLowerCase()));
          } else if (value == 'Highest Rating') {
            filteredApps.sort((a, b) => (b.ratingAvg ?? 0.0).compareTo(a.ratingAvg ?? 0.0));
          } else if (value == 'Lowest Rating') {
            filteredApps.sort((a, b) => (a.ratingAvg ?? 0.0).compareTo(b.ratingAvg ?? 0.0));
          }
          break;
        case 'Category':
          filteredApps = filteredApps.where((app) => app.category == (value as Category).id).toList();
          break;
        case 'Rating':
          value = value as String;
          value = value.replaceAll('+ Stars', '');
          filteredApps = filteredApps.where((app) => (app.ratingAvg ?? 0.0) >= double.parse(value)).toList();
          break;
        case 'Capabilities':
          filteredApps = filteredApps.where((app) => app.capabilities.contains((value as AppCapability).id)).toList();
          break;
        default:
          break;
      }
    });
    notifyListeners();
  }

  void setIsLoading(bool value) {
    isLoading = value;
    notifyListeners();
  }

  void setSelectedChatAppId(String? appId) {
    if (appId == null) {
      selectedChatAppId = SharedPreferencesUtil().selectedChatAppId;
    } else {
      selectedChatAppId = appId;
      SharedPreferencesUtil().selectedChatAppId = appId;
    }
    notifyListeners();
  }

  App? getSelectedApp() {
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
    if (isLoading) return;
    setIsLoading(true);
    apps = await retrieveApps();
    appLoading = List.filled(apps.length, false, growable: true);
    setIsLoading(false);
    notifyListeners();
  }

  void updateLocalApp(App app) {
    var idx = apps.indexWhere((element) => element.id == app.id);
    if (idx != -1) {
      apps[idx] = app;
      updatePrefApps();
      setApps();
    }
    notifyListeners();
  }

  void updateLocalAppReviewResponse(String appId, String response, String reviewId) {
    var idx = apps.indexWhere((element) => element.id == appId);
    if (idx != -1) {
      apps[idx].updateReviewResponse(response, reviewId, DateTime.now());
      updatePrefApps();
      setApps();
    }
    notifyListeners();
  }

  void checkIsAppOwner(String? appUid) {
    if (appUid != null) {
      if (appUid == SharedPreferencesUtil().uid) {
        isAppOwner = true;
      } else {
        isAppOwner = false;
      }
    } else {
      isAppOwner = false;
    }
    notifyListeners();
  }

  void setIsAppPublicToggled(bool value) {
    appPublicToggled = value;
    notifyListeners();
  }

  Future deleteApp(String appId) async {
    var res = await deleteAppServer(appId);
    if (res) {
      var appIndex = apps.indexWhere((app) => app.id == appId);
      apps.removeAt(appIndex);
      filteredApps.removeWhere((app) => app.id == appId);
      appLoading.removeAt(appIndex);
      updatePrefApps();
      setApps();
      AppSnackbar.showSnackbarSuccess('App deleted successfully 🗑️');
    } else {
      AppSnackbar.showSnackbarError('Failed to delete app. Please try again later.');
    }
    notifyListeners();
  }

  void toggleAppPublic(String appId, bool value) {
    appPublicToggled = value;
    changeAppVisibilityServer(appId, value);
    getApps();
    var appIndex = apps.indexWhere((app) => app.id == appId);
    apps[appIndex].private = !value;
    updatePrefApps();
    setApps();
    AppSnackbar.showSnackbarSuccess('App visibility changed successfully. It may take a few minutes to reflect.');
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
    notifyListeners();
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

  Future<void> toggleApp(String appId, bool isEnabled, int? idx) async {
    if (idx != null) {
      if (appLoading[idx]) return;
      appLoading[idx] = true;
      notifyListeners();
    }

    var prefs = SharedPreferencesUtil();
    if (isEnabled) {
      var enabled = await enableAppServer(appId);
      if (!enabled) {
        AppDialog.show(
          title: 'Error activating the app',
          content: 'If this is an integration app, make sure the setup is completed.',
          singleButton: true,
        );
        if (idx != null) {
          appLoading[idx] = false;
          notifyListeners();
        }

        return;
      }
      prefs.enableApp(appId);
      MixpanelManager().appEnabled(appId);
    } else {
      await disableAppServer(appId);
      prefs.disableApp(appId);
      MixpanelManager().appDisabled(appId);
    }
    if (idx != null) {
      appLoading[idx] = false;
    }
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
