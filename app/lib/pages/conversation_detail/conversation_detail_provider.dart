import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';

class ConversationDetailProvider extends ChangeNotifier with MessageNotifierMixin {
  AppProvider? appProvider;
  ConversationProvider? conversationProvider;

  // late ServerConversation memory;

  DateTime selectedDate = DateTime.now();
  String? _cachedConversationId;

  bool isLoading = false;
  bool loadingReprocessConversation = false;
  String reprocessConversationId = '';
  App? selectedAppForReprocessing;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  final List<App> _cachedEnabledConversationApps = [];
  final List<App> _cachedSuggestedApps = [];
  final Set<String> _locallyAddedAppIds = {};

  List<App> get appsList => appProvider?.apps ?? [];

  List<App> get cachedEnabledConversationApps => _cachedEnabledConversationApps;

  List<App> get cachedSuggestedApps => _cachedSuggestedApps;

  Structured get structured {
    return conversation.structured;
  }

  ServerConversation? _cachedConversation;
  ServerConversation get conversation {
    final list = conversationProvider?.groupedConversations[selectedDate];
    final id = _cachedConversationId;

    ServerConversation? result;

    if (list != null && list.isNotEmpty) {
      if (id != null) {
        result = list.firstWhereOrNull((c) => c.id == id);
      }
      result ??= list.first;
      _cachedConversationId = result.id;
    }

    result ??= _cachedConversation;
    if (result != null &&
        result.createdAt.year == selectedDate.year &&
        result.createdAt.month == selectedDate.month &&
        result.createdAt.day == selectedDate.day) {
      return _cachedConversation = result;
    }

    if (_cachedConversation != null) {
      return _cachedConversation!;
    }

    throw StateError("No valid conversation found");
  }

  List<bool> appResponseExpanded = [];

  TextEditingController? titleController;
  FocusNode? titleFocusNode;

  bool isTranscriptExpanded = false;

  bool canDisplaySeconds = true;

  bool hasAudioRecording = false;

  bool editSegmentLoading = false;

  bool showUnassignedFloatingButton = true;

  void toggleEditSegmentLoading(bool value) {
    editSegmentLoading = value;
    notifyListeners();
  }

  void setShowUnassignedFloatingButton(bool value) {
    showUnassignedFloatingButton = value;
    notifyListeners();
  }

  void toggleIsTranscriptExpanded() {
    isTranscriptExpanded = !isTranscriptExpanded;
    notifyListeners();
  }

  void setProviders(AppProvider provider, ConversationProvider conversationProvider) {
    this.conversationProvider = conversationProvider;
    appProvider = provider;
    notifyListeners();
  }

  updateLoadingState(bool loading) {
    isLoading = loading;
    notifyListeners();
  }

  updateReprocessConversationLoadingState(bool loading) {
    loadingReprocessConversation = loading;
    if (!loading) {
      selectedAppForReprocessing = null;
    }
    notifyListeners();
  }

  void setSelectedAppForReprocessing(App app) {
    selectedAppForReprocessing = app;
    notifyListeners();
  }

  void clearSelectedAppForReprocessing() {
    selectedAppForReprocessing = null;
    notifyListeners();
  }

  void updateReprocessConversationId(String id) {
    reprocessConversationId = id;
    notifyListeners();
  }

  void updateConversation(String conversationId, DateTime date) {
    final list = conversationProvider?.groupedConversations[date];
    if (list != null) {
      final conv = list.firstWhereOrNull((c) => c.id == conversationId);
      if (conv != null) {
        selectedDate = date;
        _cachedConversationId = conv.id;
        _cachedConversation = conv;
        appResponseExpanded = List.filled(conv.appResults.length, false);
        notifyListeners();
      }
    }
  }

  void updateEventState(bool state, int i) {
    conversation.structured.events[i].created = state;
    notifyListeners();
  }

  void updateActionItemState(bool state, int i) {
    conversation.structured.actionItems[i].completed = state;
    notifyListeners();
  }

  List<ActionItem> deletedActionItems = [];

  void deleteActionItem(int i) {
    deletedActionItems.add(conversation.structured.actionItems[i]);
    conversation.structured.actionItems.removeAt(i);
    notifyListeners();
  }

  void undoDeleteActionItem(int idx) {
    conversation.structured.actionItems.insert(idx, deletedActionItems.removeLast());
    notifyListeners();
  }

  void deleteActionItemPermanently(ActionItem item, int itemIdx) {
    deletedActionItems.removeWhere((element) => element == item);
    deleteConversationActionItem(conversation.id, item);
    notifyListeners();
  }

  void updateAppResponseExpanded(int index) {
    appResponseExpanded[index] = !appResponseExpanded[index];
    notifyListeners();
  }

  bool hasConversationSummaryRatingSet = false;
  Timer? _ratingTimer;
  bool showRatingUI = false;

  void setShowRatingUi(bool value) {
    showRatingUI = value;
    notifyListeners();
  }

  void setConversationRating(int value) {
    setConversationSummaryRating(conversation.id, value);
    hasConversationSummaryRatingSet = true;
    setShowRatingUi(false);
  }

  Future initConversation() async {
    // updateLoadingState(true);
    titleController?.dispose();
    titleFocusNode?.dispose();
    _ratingTimer?.cancel();
    showRatingUI = false;
    hasConversationSummaryRatingSet = false;

    titleController = TextEditingController();
    titleFocusNode = FocusNode();

    showUnassignedFloatingButton = true;

    titleController!.text = conversation.structured.title;
    titleFocusNode!.addListener(() {
      print('titleFocusNode focus changed');
      if (!titleFocusNode!.hasFocus) {
        conversation.structured.title = titleController!.text;
        updateConversationTitle(conversation.id, titleController!.text);
      }
    });

    canDisplaySeconds = TranscriptSegment.canDisplaySeconds(conversation.transcriptSegments);

    loadPreferredSummarizationApp();

    fetchAndCacheEnabledConversationApps();

    if (conversation.hasAudio()) {
      precacheConversationAudio(conversation.id);
    }

    if (!conversation.discarded) {
      getHasConversationSummaryRating(conversation.id).then((value) {
        hasConversationSummaryRatingSet = value;
        notifyListeners();
        if (!hasConversationSummaryRatingSet) {
          _ratingTimer = Timer(const Duration(seconds: 15), () {
            if (_ratingTimer?.isActive ?? false) {
              setConversationSummaryRating(conversation.id, -1);
              showRatingUI = true;
              notifyListeners();
            }
          });
        }
      });
    }

    // updateLoadingState(false);
    notifyListeners();
  }

  Future<bool> reprocessConversation({String? appId}) async {
    debugPrint('_reProcessConversation with appId: $appId');
    updateReprocessConversationLoadingState(true);
    updateReprocessConversationId(conversation.id);
    try {
      var updatedConversation = await reProcessConversationServer(conversation.id, appId: appId);
      MixpanelManager().reProcessConversation(conversation);
      updateReprocessConversationLoadingState(false);
      updateReprocessConversationId('');
      if (updatedConversation == null) {
        notifyError('REPROCESS_FAILED');
        notifyListeners();
        return false;
      }

      // else
      conversationProvider!.updateConversation(updatedConversation);
      SharedPreferencesUtil().modifiedConversationDetails = updatedConversation;

      _cachedConversation = updatedConversation;

      AppResponse? summaryApp = getSummarizedApp();
      if (summaryApp != null && summaryApp.appId != null && appProvider != null) {
        String appId = summaryApp.appId!;
        bool appExists = appProvider!.apps.any((app) => app.id == appId);
        if (!appExists) {
          await appProvider!.getApps();
        }
      }
      notifyInfo('REPROCESS_SUCCESS');
      notifyListeners();
      return true;
    } catch (err, stacktrace) {
      print(err);
      var conversationReporting = MixpanelManager().getConversationEventProperties(conversation);
      await PlatformManager.instance.crashReporter.reportCrash(err, stacktrace, userAttributes: {
        'conversation_transcript_length': conversationReporting['transcript_length'].toString(),
        'conversation_transcript_word_count': conversationReporting['transcript_word_count'].toString(),
      });
      notifyError('REPROCESS_FAILED');
      updateReprocessConversationLoadingState(false);
      updateReprocessConversationId('');
      notifyListeners();
      return false;
    }
  }

  void unassignConversationTranscriptSegment(String conversationId, String segmentId) {
    final segmentIdx = conversation.transcriptSegments.indexWhere((s) => s.id == segmentId);
    if (segmentIdx == -1) return;
    conversation.transcriptSegments[segmentIdx].isUser = false;
    conversation.transcriptSegments[segmentIdx].personId = null;
    assignBulkConversationTranscriptSegments(conversationId, [segmentId]);
    notifyListeners();
  }

  AppResponse? getSummarizedApp() {
    if (conversation.appResults.isNotEmpty) {
      return conversation.appResults[0];
    }
    if (conversation.structured.overview.isNotEmpty) {
      return AppResponse(
        conversation.structured.overview,
        appId: null,
      );
    }
    return null;
  }

  List<String> getSuggestedApps() {
    return conversation.suggestedSummarizationApps;
  }

  List<App> getAvailableSuggestedApps() {
    final suggestedAppIds = getSuggestedApps();
    if (suggestedAppIds.isEmpty || appProvider == null) return [];

    return appProvider!.apps
        .where((app) => suggestedAppIds.contains(app.id) && app.worksWithMemories() && app.enabled)
        .toList();
  }

  Future<List<App>> getSuggestedAppsFromAPI() async {
    try {
      return await getConversationSuggestedApps(conversation.id);
    } catch (e) {
      debugPrint('Error fetching suggested apps: $e');
      return [];
    }
  }

  Future<List<App>> getEnabledConversationAppsFromAPI() async {
    try {
      final result = await retrieveAppsSearch(installedApps: true, limit: 100);
      return result.apps.where((app) => app.worksWithMemories() && app.enabled).toList();
    } catch (e) {
      debugPrint('Error fetching enabled conversation apps: $e');
      return [];
    }
  }

  Future<void> fetchAndCacheEnabledConversationApps() async {
    try {
      final apps = await getEnabledConversationAppsFromAPI();

      final locallyAddedApps =
          _cachedEnabledConversationApps.where((app) => _locallyAddedAppIds.contains(app.id)).toList();

      _cachedEnabledConversationApps.clear();
      _cachedEnabledConversationApps.addAll(apps);

      for (final localApp in locallyAddedApps) {
        if (!apps.any((app) => app.id == localApp.id)) {
          _cachedEnabledConversationApps.add(localApp);
        } else {
          _locallyAddedAppIds.remove(localApp.id);
        }
      }

      notifyListeners();
    } catch (e) {
      debugPrint('Error fetching and caching enabled conversation apps: $e');
    }
  }

  Future<void> fetchAndCacheSuggestedApps() async {
    try {
      final apps = await getSuggestedAppsFromAPI();
      _cachedSuggestedApps.clear();
      _cachedSuggestedApps.addAll(apps);
      notifyListeners();
    } catch (e) {
      debugPrint('Error fetching and caching suggested apps: $e');
    }
  }

  App? findAppById(String? appId) {
    if (appId == null) return null;

    final enabledApp = _cachedEnabledConversationApps.firstWhereOrNull((app) => app.id == appId);
    if (enabledApp != null) return enabledApp;

    final suggestedApp = _cachedSuggestedApps.firstWhereOrNull((app) => app.id == appId);
    if (suggestedApp != null) return suggestedApp;

    return null;
  }

  Future<bool> enableApp(App app) async {
    try {
      final success = await enableAppServer(app.id);

      if (success) {
        SharedPreferencesUtil().enableApp(app.id);

        app.enabled = true;

        final existingIndex = _cachedEnabledConversationApps.indexWhere((a) => a.id == app.id);
        if (existingIndex == -1) {
          _cachedEnabledConversationApps.add(app);
        } else {
          _cachedEnabledConversationApps[existingIndex] = app;
        }

        notifyListeners();
      }

      return success;
    } catch (e) {
      debugPrint('Error enabling app ${app.id}: $e');
      return false;
    }
  }

  void addToEnabledConversationApps(App app) {
    final existingIndex = _cachedEnabledConversationApps.indexWhere((a) => a.id == app.id);
    if (existingIndex == -1) {
      _cachedEnabledConversationApps.add(app);
    } else {
      _cachedEnabledConversationApps[existingIndex] = app;
    }
    _locallyAddedAppIds.add(app.id);
    notifyListeners();
  }

  bool isAppSuggested(String appId) {
    return getSuggestedApps().contains(appId);
  }

  bool isSuggestedAppAvailable(String appId) {
    if (appProvider == null) return false;
    return appProvider!.apps.any((app) => app.id == appId && app.worksWithMemories() && app.enabled);
  }

  void setCachedConversation(ServerConversation conversation) {
    _cachedConversation = conversation;
    _cachedConversationId = conversation.id;
    notifyListeners();
  }

  Future<void> refreshConversation() async {
    try {
      final updatedConversation = await getConversationById(conversation.id);
      if (updatedConversation != null) {
        _cachedConversation = updatedConversation;
        conversationProvider?.updateConversation(updatedConversation);
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error refreshing conversation: $e');
    }
  }

  void updateFolderIdLocally(String? newFolderId) {
    if (_cachedConversation != null) {
      _cachedConversation!.folderId = newFolderId;
      conversationProvider?.updateConversation(_cachedConversation!);
      notifyListeners();
    }
  }

  String? _preferredSummarizationAppId;

  String? get preferredSummarizationAppId => _preferredSummarizationAppId;

  void setPreferredSummarizationApp(String appId) {
    _preferredSummarizationAppId = appId;
    setPreferredSummarizationAppServer(appId);
    SharedPreferencesUtil().preferredSummarizationAppId = appId;
    notifyListeners();
  }

  void loadPreferredSummarizationApp() {
    _preferredSummarizationAppId = SharedPreferencesUtil().preferredSummarizationAppId;
  }

  void trackLastUsedSummarizationApp(String appId) {
    SharedPreferencesUtil().lastUsedSummarizationAppId = appId;
    notifyListeners();
  }

  String? getLastUsedSummarizationAppId() {
    final lastUsedId = SharedPreferencesUtil().lastUsedSummarizationAppId;
    return lastUsedId.isEmpty ? null : lastUsedId;
  }

  App? getLastUsedSummarizationApp() {
    final lastUsedId = getLastUsedSummarizationAppId();
    if (lastUsedId == null || appProvider == null) return null;

    return appProvider!.apps.firstWhereOrNull(
      (app) => app.id == lastUsedId && app.worksWithMemories() && app.enabled,
    );
  }

  @override
  void dispose() {
    _ratingTimer?.cancel();
    super.dispose();
  }
}