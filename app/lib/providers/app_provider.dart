import 'package:collection/collection.dart';
import 'package:flutter/widgets.dart';
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:omi/utils/alerts/app_dialog.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class AppProvider extends BaseProvider {
  List<App> apps = [];
  List<App> popularApps = [];

  bool filterChat = true;
  bool filterMemories = true;
  bool filterExternal = true;
  String searchQuery = '';
  bool installedAppsOptionSelected = true;

  List<bool> appLoading = [];

  String selectedChatAppId = "";

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

  Future<App?> getAppFromId(String id) async {
    if (apps.isEmpty) {
      apps = SharedPreferencesUtil().appsList;
    }
    var app = apps.firstWhereOrNull((app) => app.id == id);
    if (app == null) {
      var appRes = await getAppDetailsServer(id);
      if (appRes != null) {
        app = App.fromJson(appRes);
      }
      return app;
    }
    return app;
  }

  Future<App?> getAppDetails(String id) async {
    var app = await getAppDetailsServer(id);
    if (app != null) {
      var oldApp = apps.where((element) => element.id == id).firstOrNull;
      if (oldApp == null) {
        return null;
      }
      var idx = apps.indexOf(oldApp);
      apps[idx] = App.fromJson(app);
      notifyListeners();
      return apps[idx];
    }
    return null;
  }

  void updateInstalledAppsOptionSelected(bool value) {
    installedAppsOptionSelected = value;
    notifyListeners();
  }

  void addOrRemoveFilter(String filter, String filterGroup) {
    if (filters.containsKey(filterGroup)) {
      if (filters[filterGroup] == filter) {
        filters.remove(filterGroup);
      } else {
        filters[filterGroup] = filter;
      }
    } else {
      filters.addAll({filterGroup: filter});
    }
    filterApps();
    notifyListeners();
  }

  void addOrRemoveCategoryFilter(Category category) {
    if (filters.containsKey('Category')) {
      if (filters['Category'] == category) {
        filters.remove('Category');
      } else {
        filters['Category'] = category;
      }
    } else {
      filters.addAll({'Category': category});
    }
    filterApps();
    notifyListeners();
  }

  void addOrRemoveCapabilityFilter(AppCapability capability) {
    if (filters.containsKey('Capabilities')) {
      if (filters['Capabilities'] == capability) {
        filters.remove('Capabilities');
      } else {
        filters['Capabilities'] = capability;
      }
    } else {
      filters.addAll({'Capabilities': capability});
    }
    filterApps();
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
    filterApps();
    notifyListeners();
  }

  void removeFilter(String filterGroup) {
    filters.remove(filterGroup);
    filterApps();
    notifyListeners();
  }

  bool isFilterActive() {
    return filters.isNotEmpty;
  }

  bool isSearchActive() {
    return searchQuery.isNotEmpty;
  }

  void searchApps(String query) {
    searchQuery = query.toLowerCase();
    filterApps();
    notifyListeners();
  }

  void filterApps() {
    Iterable<App> currentlyFiltered = apps;

    filters.forEach((key, value) {
      switch (key) {
        case 'Apps':
          if (value == 'Installed Apps') {
            currentlyFiltered = currentlyFiltered.where((app) => app.enabled);
          } else if (value == 'My Apps') {
            currentlyFiltered = currentlyFiltered.where((app) => app.isOwner(SharedPreferencesUtil().uid));
          }
          break;
        case 'Category':
          if (value is Category) {
            currentlyFiltered = currentlyFiltered.where((app) => app.category == value.id);
          }
          break;
        case 'Rating':
          if (value is String) {
            String ratingStr = value.replaceAll('+ Stars', '');
            double minRating = double.tryParse(ratingStr) ?? 0.0;
            currentlyFiltered = currentlyFiltered.where((app) => (app.ratingAvg ?? 0.0) >= minRating);
          }
          break;
        case 'Capabilities':
          if (value is AppCapability) {
            currentlyFiltered = currentlyFiltered.where((app) => app.capabilities.contains(value.id));
          }
          break;
        default:
          break;
      }
    });

    if (searchQuery.isNotEmpty) {
      currentlyFiltered = currentlyFiltered.where((app) => app.name.toLowerCase().contains(searchQuery));
    }

    List<App> finalFilteredList = currentlyFiltered.toList();

    final Comparator<App>? comparator = _getSortComparator();
    if (comparator != null) {
      finalFilteredList.sort(comparator);
    }

    filteredApps = finalFilteredList;
  }

  void setIsLoading(bool value) {
    isLoading = value;
    notifyListeners();
  }

  void setSelectedChatAppId(String? appId) {
    selectedChatAppId = appId ?? "";
    notifyListeners();
  }

  App? getSelectedApp() {
    return apps.firstWhereOrNull((p) => p.id == selectedChatAppId);
  }

  void setAppLoading(int index, bool value) {
    if (index >= 0 && index < appLoading.length) {
      // Boundary check
      appLoading[index] = value;
      notifyListeners();
    } else {
      print("Error: Attempted to set loading state for invalid index $index");
    }
  }

  void clearSearchQuery() {
    searchQuery = '';
    filterApps(); // Re-apply filters without search
    notifyListeners();
  }

  Future getApps() async {
    if (isLoading) return;
    setIsLoading(true);
    apps = await retrieveApps();
    appLoading = List.filled(apps.length, false, growable: true);
    filterApps();
    setIsLoading(false);
  }

  Future getPopularApps() async {
    setIsLoading(true);
    popularApps = await retrievePopularApps();
    setIsLoading(false);
  }

  void updateLocalApp(App app) {
    var idx = apps.indexWhere((element) => element.id == app.id);
    if (idx != -1) {
      apps[idx] = app;
      updatePrefApps();
      // filterApps();
      var filteredIdx = filteredApps.indexWhere((element) => element.id == app.id);
      if (filteredIdx != -1) {
        filteredApps[filteredIdx] = app;
      }
      notifyListeners(); // Notify after potential changes
    }
  }

  void updateLocalAppReviewResponse(String appId, String response, String reviewId) {
    var idx = apps.indexWhere((element) => element.id == appId);
    if (idx != -1) {
      apps[idx].updateReviewResponse(response, reviewId, DateTime.now());
      updatePrefApps();
      var filteredIdx = filteredApps.indexWhere((element) => element.id == appId);
      if (filteredIdx != -1) {
        filteredApps[filteredIdx] = apps[idx];
      }
      notifyListeners();
    }
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
      if (appIndex != -1) {
        apps.removeAt(appIndex);
        if (appIndex < appLoading.length) {
          appLoading.removeAt(appIndex);
        }
        filteredApps.removeWhere((app) => app.id == appId);
        updatePrefApps();
        AppSnackbar.showSnackbarSuccess('App deleted successfully 🗑️');
        notifyListeners();
      } else {
        print("Warning: Tried to delete app $appId but it wasn't found in the 'apps' list.");
      }
    } else {
      AppSnackbar.showSnackbarError('Failed to delete app. Please try again later.');
    }
  }

  void toggleAppPublic(String appId, bool value) {
    appPublicToggled = value;
    changeAppVisibilityServer(appId, value);
    var appIndex = apps.indexWhere((app) => app.id == appId);
    if (appIndex != -1) {
      apps[appIndex].private = !value;
      updatePrefApps();
      var filteredIdx = filteredApps.indexWhere((app) => app.id == appId);
      if (filteredIdx != -1) {
        filteredApps[filteredIdx] = apps[appIndex];
      }
      AppSnackbar.showSnackbarSuccess('App visibility changed successfully. It may take a few minutes to reflect.');
      notifyListeners();
    }
    // TODO: Consider calling getApps() after a delay or pull-to-refresh
    // to get server-confirmed state later, but avoid immediate perf hit.
    // getApps(); // This would re-fetch everything
  }

  void setAppsFromCache() {
    if (SharedPreferencesUtil().appsList.isNotEmpty) {
      apps = SharedPreferencesUtil().appsList;
      filterApps();
      notifyListeners();
    }
  }

  void updatePrefApps() {
    SharedPreferencesUtil().appsList = apps;
  }

  void setApps() {
    apps = SharedPreferencesUtil().appsList;
    filterApps();
    notifyListeners();
  }

  // Helper: Checks if app matches current filters (used by _updateFilteredAppStatus)
  bool _doesAppMatchFilters(App app) {
    bool matchesBaseFilters = true;
    if (filters.isNotEmpty) {
      matchesBaseFilters = filters.entries.every((entry) {
        final key = entry.key;
        final value = entry.value;
        bool match = true; // Assume match until proven otherwise

        switch (key) {
          case 'Apps':
            if (value == 'Installed Apps') {
              match = app.enabled;
            } else if (value == 'My Apps') {
              match = app.isOwner(SharedPreferencesUtil().uid);
            }
            break;
          case 'Category':
            if (value is Category) {
              match = app.category == value.id;
            } else {
              match = false;
            }
            break;
          case 'Rating':
            if (value is String) {
              String ratingStr = value.replaceAll('+ Stars', '');
              double minRating = double.tryParse(ratingStr) ?? 0.0;
              match = (app.ratingAvg ?? 0.0) >= minRating;
            } else {
              match = false;
            }
            break;
          case 'Capabilities':
            if (value is AppCapability) {
              match = app.capabilities.contains(value.id);
            } else {
              match = false;
            }
            break;
          default:
            break;
        }
        return match;
      });
    }

    bool matchesSearch = searchQuery.isEmpty || app.name.toLowerCase().contains(searchQuery);

    return matchesBaseFilters && matchesSearch;
  }

  // Helper: Gets the comparator for sorting
  Comparator<App>? _getSortComparator() {
    if (filters.containsKey('Sort')) {
      final sortValue = filters['Sort'];
      switch (sortValue) {
        case 'A-Z':
          return (a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase());
        case 'Z-A':
          return (a, b) => b.name.toLowerCase().compareTo(a.name.toLowerCase());
        case 'Highest Rating':
          return (a, b) => (b.ratingAvg ?? -1.0).compareTo(a.ratingAvg ?? -1.0);
        case 'Lowest Rating':
          return (a, b) => (a.ratingAvg ?? -1.0).compareTo(b.ratingAvg ?? -1.0);
        default:
          return null;
      }
    }
    return null;
  }

  void _updateFilteredAppStatus(App toggledApp) {
    final bool matchesFiltersNow = _doesAppMatchFilters(toggledApp);
    final int existingIndex = filteredApps.indexWhere((a) => a.id == toggledApp.id);
    final bool isInFilteredList = existingIndex != -1;
    final Comparator<App>? comparator = _getSortComparator();

    if (matchesFiltersNow) {
      if (!isInFilteredList) {
        if (comparator != null && filteredApps.isNotEmpty) {
          int insertIndex = lowerBound(filteredApps, toggledApp, compare: comparator);
          filteredApps.insert(insertIndex, toggledApp);
        } else {
          filteredApps.add(toggledApp);
          if (comparator != null && filteredApps.length > 1) {
            filteredApps.sort(comparator);
          }
        }
      } else {
        filteredApps[existingIndex] = toggledApp;
      }
    } else {
      if (isInFilteredList) {
        filteredApps.removeAt(existingIndex);
      }
    }
  }

  Future<void> toggleApp(String appId, bool isEnabled, int? idx) async {
    int loadingIndex = -1;
    if (idx != null && idx >= 0 && idx < appLoading.length) {
      loadingIndex = idx;
      if (appLoading[loadingIndex]) return;
      appLoading[loadingIndex] = true;
      notifyListeners();
    } else if (idx != null) {
      debugPrint("Warning: Invalid index $idx provided to toggleApp.");
    }

    var prefs = SharedPreferencesUtil();
    bool success = false;
    String? errorMessage;

    try {
      if (isEnabled) {
        success = await enableAppServer(appId);
        if (!success) {
          errorMessage = 'Error activating the app. If this is an integration app, make sure the setup is completed.';
        } else {
          MixpanelManager().appEnabled(appId);
        }
      } else {
        await disableAppServer(appId);
        success = true;
        MixpanelManager().appDisabled(appId);
      }
    } catch (e) {
      print('Error toggling app $appId: $e');
      success = false;
      errorMessage = 'An error occurred while updating the app status.';
    }

    if (!success && errorMessage != null) {
      AppDialog.show(
        title: 'Error',
        content: errorMessage,
        singleButton: true,
      );
    }

    if (success) {
      if (isEnabled) {
        prefs.enableApp(appId);
      } else {
        prefs.disableApp(appId);
      }

      var appIndex = apps.indexWhere((a) => a.id == appId);
      if (appIndex != -1) {
        apps[appIndex].enabled = isEnabled;
        App toggledApp = apps[appIndex];

        _updateFilteredAppStatus(toggledApp);
      } else {
        debugPrint("Error: Toggled app $appId not found in local 'apps' list after successful toggle.");
      }
    }

    if (loadingIndex != -1) {
      appLoading[loadingIndex] = false;
    }
    notifyListeners();
  }
}
