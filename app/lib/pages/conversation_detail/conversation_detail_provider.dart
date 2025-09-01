import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';
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

  int conversationIdx = 0;
  DateTime selectedDate = DateTime.now();

  bool isLoading = false;
  bool loadingReprocessConversation = false;
  String reprocessConversationId = '';
  App? selectedAppForReprocessing;

  final scaffoldKey = GlobalKey<ScaffoldState>();
  List<App> get appsList => appProvider?.apps ?? [];

  Structured get structured {
    return conversation.structured;
  }

  ServerConversation? _cachedConversation;
  ServerConversation get conversation {
    if (conversationProvider == null ||
        !conversationProvider!.groupedConversations.containsKey(selectedDate) ||
        conversationProvider!.groupedConversations[selectedDate] == null ||
        conversationProvider!.groupedConversations[selectedDate]!.length <= conversationIdx) {
      // Return cached conversation if available, otherwise create an empty one
      if (_cachedConversation == null) {
        throw StateError("No conversation available");
      }
      return _cachedConversation!;
    }
    _cachedConversation = conversationProvider!.groupedConversations[selectedDate]![conversationIdx];
    return _cachedConversation!;
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

  void updateConversation(int memIdx, DateTime date) {
    conversationIdx = memIdx;
    selectedDate = date;
    appResponseExpanded = List.filled(conversation.appResults.length, false);
    notifyListeners();
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

    if (!conversation.discarded) {
      getHasConversationSummaryRating(conversation.id).then((value) {
        hasConversationSummaryRatingSet = value;
        notifyListeners();
        if (!hasConversationSummaryRatingSet) {
          _ratingTimer = Timer(const Duration(seconds: 15), () {
            setConversationSummaryRating(conversation.id, -1); // set -1 to indicate is was shown
            showRatingUI = true;
            notifyListeners();
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

      // Update the cached conversation to ensure we have the latest data
      _cachedConversation = updatedConversation;

      // Check if the summarized app is in the apps list
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

  /// Returns the first app result from the conversation if available
  /// This is typically the summary of the conversation
  AppResponse? getSummarizedApp() {
    if (conversation.appResults.isNotEmpty) {
      return conversation.appResults[0];
    }
    // If no appResults but we have structured overview, create a fake AppResponse
    if (conversation.structured.overview.isNotEmpty) {
      return AppResponse(
        conversation.structured.overview,
        appId: null,
      );
    }
    return null;
  }

  /// Returns the list of suggested summarization apps for this conversation
  List<String> getSuggestedApps() {
    return conversation.suggestedSummarizationApps;
  }

  /// Returns the list of suggested apps that are available in the current apps list
  List<App> getAvailableSuggestedApps() {
    final suggestedAppIds = getSuggestedApps();
    if (suggestedAppIds.isEmpty || appProvider == null) return [];

    return appProvider!.apps
        .where((app) => suggestedAppIds.contains(app.id) && app.worksWithMemories() && app.enabled)
        .toList();
  }

  /// Returns the list of suggested apps from the API (includes unavailable apps)
  Future<List<App>> getSuggestedAppsFromAPI() async {
    try {
      return await getConversationSuggestedApps(conversation.id);
    } catch (e) {
      debugPrint('Error fetching suggested apps: $e');
      return [];
    }
  }

  /// Checks if an app is in the suggested apps list
  bool isAppSuggested(String appId) {
    return getSuggestedApps().contains(appId);
  }

  /// Checks if a suggested app is available/enabled for the user
  bool isSuggestedAppAvailable(String appId) {
    if (appProvider == null) return false;
    return appProvider!.apps.any((app) => app.id == appId && app.worksWithMemories() && app.enabled);
  }

  void setCachedConversation(ServerConversation conversation) {
    _cachedConversation = conversation;
    notifyListeners();
  }

  void setPreferredSummarizationApp(String appId) {
    setPreferredSummarizationAppServer(appId);
    notifyListeners();
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
}
