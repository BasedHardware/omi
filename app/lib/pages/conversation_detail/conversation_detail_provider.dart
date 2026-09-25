import 'package:flutter/material.dart';

import 'package:clock/clock.dart';
import 'package:collection/collection.dart';
import 'package:flutter_provider_utilities/flutter_provider_utilities.dart';

import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/http/api/audio.dart';
import 'package:omi/backend/http/api/conversations.dart'
    hide unlinkCalendarEvent, autoLinkCalendarEvent, linkCalendarEvent;
import 'package:omi/backend/http/api/conversations.dart' as conv_api
    show unlinkCalendarEvent, autoLinkCalendarEvent, linkCalendarEvent;
import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_summary_selection.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

typedef SpeakerAssignmentCall = Future<bool> Function(String, List<String>,
    {bool? isUser, String? personId, int? speakerId});
typedef ConversationReprocessCall = Future<ServerConversation?> Function(String, {String? appId});

class ConversationDetailProvider extends ChangeNotifier with MessageNotifierMixin {
  ConversationDetailProvider({SpeakerAssignmentCall? assignSpeaker, ConversationReprocessCall? reprocess})
      : _assignSpeaker = assignSpeaker ?? assignBulkConversationTranscriptSegments,
        _reprocess = reprocess ?? reProcessConversationServer;
  final SpeakerAssignmentCall _assignSpeaker;
  final ConversationReprocessCall _reprocess;
  String? _speakerSummaryConversationId;
  int _speakerEditGeneration = 0;
  bool _savingSpeaker = false;

  bool get offerSpeakerSummaryRefresh =>
      _speakerSummaryConversationId != null && _speakerSummaryConversationId == conversationOrNull?.id;

  Future<bool> assignSpeaker(List<String> segmentIds, String personId,
      {int? speakerId, String? expectedConversationId}) async {
    final target = conversation;
    if (_savingSpeaker ||
        loadingReprocessConversation ||
        segmentIds.isEmpty ||
        (expectedConversationId != null && target.id != expectedConversationId)) return false;
    final selected = target.transcriptSegments
        .where((s) => speakerId == null ? segmentIds.contains(s.id) : s.speakerId == speakerId)
        .toList();
    if (selected.isEmpty) return false;
    final self = personId == 'user';
    final person = self ? null : personId;
    final changed = selected.any((s) => s.isUser != self || s.personId != person);
    _savingSpeaker = true;
    try {
      final bool saved;
      try {
        saved =
            await _assignSpeaker(target.id, List.of(segmentIds), isUser: self, personId: person, speakerId: speakerId);
      } catch (_) {
        return false;
      }
      if (!saved) return false;
      for (final segment in selected) {
        segment.isUser = self;
        segment.personId = person;
      }
      if (!_isDisposed) {
        if (changed) {
          _speakerEditGeneration++;
          if (target.status == ConversationStatus.completed && target.structured.overview.trim().isNotEmpty) {
            _speakerSummaryConversationId = target.id;
          }
        }
        conversationProvider?.updateConversation(target);
        notifyListeners();
      }
      return true;
    } finally {
      _savingSpeaker = false;
    }
  }

  AppProvider? appProvider;
  ConversationProvider? conversationProvider;

  // late ServerConversation memory;

  DateTime selectedDate = clock.now();
  String? _cachedConversationId;

  bool isLoading = false;
  bool loadingReprocessConversation = false;
  String reprocessConversationId = '';
  App? selectedAppForReprocessing;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  // Cache enabled conversation apps and suggested apps
  final List<App> _cachedEnabledConversationApps = [];
  final List<App> _cachedSuggestedApps = [];
  // Track locally added apps (e.g., from quick template creator) to preserve during refetch
  final Set<String> _locallyAddedAppIds = {};

  List<App> get appsList => appProvider?.apps ?? [];

  /// Returns cached enabled conversation apps
  List<App> get cachedEnabledConversationApps => _cachedEnabledConversationApps;

  /// Returns cached suggested apps for current conversation
  List<App> get cachedSuggestedApps => _cachedSuggestedApps;

  Structured get structured {
    return conversation.structured;
  }

  ServerConversation? _cachedConversation;

  /// Non-throwing variant of [conversation]. Build paths must use this so a
  /// transient miss (conversation deleted under us, day-group emptied) returns
  /// null instead of throwing from inside a Consumer's builder.
  ///
  /// Once a conversation is selected this only ever resolves to that same id.
  /// Substituting another conversation would silently retarget the page, and
  /// destructive actions (delete, visibility, rename) act on whatever this
  /// returns.
  ServerConversation? get conversationOrNull {
    final list = conversationProvider?.groupedConversations[selectedDate];
    final id = _cachedConversationId;

    ServerConversation? result;

    if (list != null && list.isNotEmpty) {
      if (id != null) {
        result = list.firstWhereOrNull((c) => c.id == id);
      } else {
        result = list.first;
        _cachedConversationId = result.id;
      }
    }

    result ??= _cachedConversation;
    if (result != null && id != null && result.id != id) return null;
    if (result != null) {
      // Validate with the *same* key function the list groups by
      // (`conversationLocalDayKey` over startedAt ?? createdAt). Comparing the
      // raw UTC year/month/day instead made this getter reject a conversation
      // that is actually present in the selected day-group whenever the
      // viewer's local day differs from the UTC day — an evening conversation
      // for any UTC+ viewer, a post-UTC-midnight one for any UTC- viewer —
      // blanking the detail page it was opened from (#10976).
      final effectiveDate = result.startedAt ?? result.createdAt;
      if (conversationLocalDayKey(effectiveDate) == conversationLocalDayKey(selectedDate)) {
        return _cachedConversation = result;
      }
    }

    return null;
  }

  /// Non-null accessor for call sites that already know the conversation is
  /// valid (gestures, async handlers). Build paths use [conversationOrNull].
  ServerConversation get conversation {
    final c = conversationOrNull;
    if (c == null) throw StateError("No valid conversation found");
    return c;
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

  Future<void> saveEditingSegmentText(int segmentIndex, String newText) async {
    final segment = conversation.transcriptSegments[segmentIndex];
    final oldText = segment.text;

    if (newText.trim().isEmpty || newText.trim() == oldText) return;

    // Optimistic update
    segment.text = newText.trim();
    notifyListeners();

    final success = await updateConversationSegmentText(conversation.id, segment.id, newText.trim());
    if (!success && !_isDisposed) {
      conversation.transcriptSegments[segmentIndex].text = oldText;
      notifyListeners();
    }
  }

  Future<void> _saveEditingSummary(String? appId, String newContent) async {
    final trimmed = newContent.trim();
    if (trimmed.isEmpty) return;

    if (appId == null) {
      final editedConversation = conversation;
      final editedStructured = editedConversation.structured;
      final oldOverview = editedStructured.overview;
      final oldSections = List<Section>.from(editedStructured.sections);
      if (trimmed == oldOverview) return;

      editedStructured.overview = trimmed;
      // The first-party summary PATCH replaces the compatibility overview and
      // clears generated sections on the server. Keep the local projection in
      // the same state while the request is in flight.
      editedStructured.sections = [];
      notifyListeners();

      final success = await persistSummaryEdit(editedConversation.id, null, trimmed);
      if (!success && !_isDisposed && identical(conversationOrNull, editedConversation)) {
        // A refresh or a newer edit may have replaced this state while the
        // request was pending. Roll back only the exact optimistic snapshot
        // that this request still owns.
        if (identical(editedConversation.structured, editedStructured) &&
            editedStructured.overview == trimmed &&
            editedStructured.sections.isEmpty) {
          editedStructured.overview = oldOverview;
          editedStructured.sections = oldSections;
          notifyListeners();
        }
      }
      return;
    }

    final editedConversation = conversation;
    final index = editedConversation.appResults.indexWhere((r) => r.appId == appId);
    if (index < 0) return;
    final editedResult = editedConversation.appResults[index];
    final oldContent = editedResult.content;
    if (trimmed == oldContent) return;

    editedResult.content = trimmed;
    notifyListeners();

    final success = await persistSummaryEdit(editedConversation.id, appId, trimmed);
    if (!success && !_isDisposed && identical(conversationOrNull, editedConversation)) {
      // See the first-party branch above: never roll back over a refreshed
      // conversation, replaced result, or newer edit.
      if (index < editedConversation.appResults.length &&
          identical(editedConversation.appResults[index], editedResult) &&
          editedResult.content == trimmed) {
        editedResult.content = oldContent;
        notifyListeners();
      }
    }
  }

  /// The persistence seam keeps optimistic summary state testable without
  /// sending a request. Production delegates to the summary PATCH endpoint.
  @visibleForTesting
  Future<bool> persistSummaryEdit(String conversationId, String? appId, String content) {
    return updateConversationSummary(conversationId, appId, content);
  }

  /// Save an edit against the same summary identity used for display. Legacy
  /// app output without an id, duplicate app ids, and stale selections are
  /// read-only because the current mutation API addresses results by app id.
  Future<void> saveEditingSummarySelection(ConversationSummarySelection selection, String newContent) async {
    if (!selection.canEdit(conversation)) return;
    if (!selection.isApp) {
      await _saveEditingSummary(null, newContent);
      return;
    }
    final index = selection.resultIndex;
    if (index == null || index < 0 || index >= conversation.appResults.length) return;
    final result = conversation.appResults[index];
    if (result.appId == null) return;
    await _saveEditingSummary(result.appId, newContent);
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

  /// Saves an edited title. Resolves null when nothing changed (blank or identical text keeps the
  /// current title), true when the server accepted it, false when it did not (the old title is
  /// restored).
  Future<bool?> saveTitle(String text) async {
    final target = conversationOrNull;
    if (target == null) return null;
    final title = text.trim();
    final previous = target.structured.title;
    if (title.isEmpty || title == previous.trim()) {
      if (titleController != null && titleController!.text != previous) titleController!.text = previous;
      return null;
    }
    target.structured.title = title;
    notifyListeners();
    final saved = await updateConversationTitle(target.id, title);
    if (!saved && !_isDisposed) {
      target.structured.title = previous;
      if (_cachedConversationId == target.id && titleController != null) titleController!.text = previous;
      notifyListeners();
    }
    return saved;
  }

  /// Folds an edit made in the shared task editor back into this conversation's task list.
  void applyTaskEdit(ActionItem item, {String? description, bool? completed, bool deleted = false}) {
    final items = conversationOrNull?.structured.actionItems;
    if (items == null || !items.contains(item)) return;
    if (deleted) {
      item.deleted = true;
    } else {
      if (description != null && description.trim().isNotEmpty) item.description = description;
      if (completed != null) item.completed = completed;
    }
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

  Future initConversation() async {
    // updateLoadingState(true);
    titleController?.dispose();
    titleFocusNode?.dispose();

    titleController = TextEditingController();
    titleFocusNode = FocusNode();

    showUnassignedFloatingButton = true;

    titleController!.text = conversation.structured.title;
    // The title saves when editing ends (Done or leaving the field); the title field calls
    // [saveTitle] and reports the outcome.

    canDisplaySeconds = TranscriptSegment.canDisplaySeconds(conversation.transcriptSegments);

    loadPreferredSummarizationApp();

    fetchAndCacheEnabledConversationApps();

    // Pre-cache audio files in background
    if (conversation.hasAudio()) {
      precacheConversationAudio(conversation.id);
    }

    // updateLoadingState(false);
    notifyListeners();
  }

  Future<bool> reprocessConversation({String? appId}) async {
    if (loadingReprocessConversation || _savingSpeaker) return false;
    final target = conversation;
    final generation = _speakerEditGeneration;
    Logger.debug('_reProcessConversation with appId: $appId');
    updateReprocessConversationLoadingState(true);
    updateReprocessConversationId(conversation.id);
    try {
      var updatedConversation = await _reprocess(target.id, appId: appId);
      if (_isDisposed) return false;
      PlatformManager.instance.analytics.reProcessConversation(conversation);
      updateReprocessConversationLoadingState(false);
      updateReprocessConversationId('');
      if (updatedConversation == null) {
        notifyError('REPROCESS_FAILED');
        notifyListeners();
        return false;
      }

      // else
      conversationProvider?.updateConversation(updatedConversation);
      SharedPreferencesUtil().modifiedConversationDetails = updatedConversation;

      // Update the cached conversation to ensure we have the latest data
      if (conversationOrNull?.id == target.id) _cachedConversation = updatedConversation;
      if (generation == _speakerEditGeneration && _speakerSummaryConversationId == target.id) {
        _speakerSummaryConversationId = null;
      }

      // Check if the selected app summary is in the apps list.
      final summarySelection = getSummarySelection();
      if (summarySelection.isApp && summarySelection.appId != null && appProvider != null) {
        String appId = summarySelection.appId!;
        bool appExists = appProvider!.apps.any((app) => app.id == appId);
        if (!appExists) {
          await appProvider!.getApps();
          if (_isDisposed) return false;
        }
      }
      notifyInfo('REPROCESS_SUCCESS');
      notifyListeners();
      return true;
    } catch (err, stacktrace) {
      print(err);
      var conversationReporting = PlatformManager.instance.analytics.getConversationEventProperties(conversation);
      await PlatformManager.instance.crashReporter.reportCrash(
        err,
        stacktrace,
        userAttributes: {
          'conversation_transcript_length': conversationReporting['transcript_length'].toString(),
          'conversation_transcript_word_count': conversationReporting['transcript_word_count'].toString(),
        },
      );
      notifyError('REPROCESS_FAILED');
      updateReprocessConversationLoadingState(false);
      updateReprocessConversationId('');
      notifyListeners();
      return false;
    }
  }

  /// Returns the explicit source and body used by every summary surface.
  ConversationSummarySelection getSummarySelection() {
    return ConversationSummarySelection.select(conversation);
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
      Logger.debug('Error fetching suggested apps: $e');
      return [];
    }
  }

  /// Returns the list of enabled apps that support conversations from the API
  Future<List<App>> getEnabledConversationAppsFromAPI() async {
    try {
      final result = await retrieveAppsSearch(installedApps: true, limit: 100);
      return result.apps.where((app) => app.worksWithMemories() && app.enabled).toList();
    } catch (e) {
      Logger.debug('Error fetching enabled conversation apps: $e');
      return [];
    }
  }

  /// Fetches and caches enabled conversation apps
  /// Preserves locally added apps that may not yet be returned by the API
  Future<void> fetchAndCacheEnabledConversationApps() async {
    try {
      final apps = await getEnabledConversationAppsFromAPI();
      if (_isDisposed) return;

      // Preserve locally added apps that aren't in the API response yet
      final locallyAddedApps =
          _cachedEnabledConversationApps.where((app) => _locallyAddedAppIds.contains(app.id)).toList();

      _cachedEnabledConversationApps.clear();
      _cachedEnabledConversationApps.addAll(apps);

      // Add back locally added apps if they weren't returned by the API
      for (final localApp in locallyAddedApps) {
        if (!apps.any((app) => app.id == localApp.id)) {
          _cachedEnabledConversationApps.add(localApp);
        } else {
          // If API returned the app, remove from locally tracked set
          _locallyAddedAppIds.remove(localApp.id);
        }
      }

      notifyListeners();
    } catch (e) {
      Logger.debug('Error fetching and caching enabled conversation apps: $e');
    }
  }

  /// Fetches and caches suggested apps for the current conversation
  Future<void> fetchAndCacheSuggestedApps() async {
    try {
      final apps = await getSuggestedAppsFromAPI();
      if (_isDisposed) return;
      _cachedSuggestedApps.clear();
      _cachedSuggestedApps.addAll(apps);
      notifyListeners();
    } catch (e) {
      Logger.debug('Error fetching and caching suggested apps: $e');
    }
  }

  /// Finds an app by ID from cached apps
  App? findAppById(String? appId) {
    if (appId == null) return null;

    final enabledApp = _cachedEnabledConversationApps.firstWhereOrNull((app) => app.id == appId);
    if (enabledApp != null) return enabledApp;

    final suggestedApp = _cachedSuggestedApps.firstWhereOrNull((app) => app.id == appId);
    if (suggestedApp != null) return suggestedApp;

    // The two caches above only fill after the summary sheet fetches. The durable
    // app catalog (appProvider.apps) is loaded at startup, so a real app_id must
    // resolve here instead of rendering "Unknown App" until the sheet is opened
    // (SCA-359).
    final providerApp = appProvider?.apps.firstWhereOrNull((app) => app.id == appId);
    return providerApp;
  }

  /// Enables an app and updates the cached enabled apps list
  /// Returns true if successful, false otherwise
  Future<bool> enableApp(App app) async {
    try {
      // Make the server call to enable the app
      final (success, _) = await enableAppServer(app.id);
      if (_isDisposed) return false;

      if (success) {
        // Update SharedPreferences
        SharedPreferencesUtil().enableApp(app.id);

        // Update the app's enabled state
        app.enabled = true;

        // Add to cached enabled apps if not already there
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
      Logger.debug('Error enabling app ${app.id}: $e');
      return false;
    }
  }

  /// Adds an app to the cached enabled conversation apps list
  /// Used when a new app is created and installed from the quick template creator
  void addToEnabledConversationApps(App app) {
    final existingIndex = _cachedEnabledConversationApps.indexWhere((a) => a.id == app.id);
    if (existingIndex == -1) {
      _cachedEnabledConversationApps.add(app);
    } else {
      _cachedEnabledConversationApps[existingIndex] = app;
    }
    // Track this as a locally added app so it's preserved during refetch
    _locallyAddedAppIds.add(app.id);
    notifyListeners();
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
    _cachedConversationId = conversation.id;
    notifyListeners();
  }

  Future<void> refreshConversation() async {
    try {
      final updatedConversation = await getConversationById(conversation.id);
      if (_isDisposed) return;
      if (updatedConversation != null) {
        _cachedConversation = updatedConversation;
        conversationProvider?.updateConversation(updatedConversation);
        notifyListeners();
      }
    } catch (e) {
      Logger.debug('Error refreshing conversation: $e');
    }
  }

  void updateFolderIdLocally(String? newFolderId) {
    if (_cachedConversation != null) {
      _cachedConversation!.folderId = newFolderId;
      conversationProvider?.updateConversation(_cachedConversation!);
      notifyListeners();
    }
  }

  void updateVisibilityLocally(ConversationVisibility newVisibility) {
    if (_cachedConversation != null) {
      _cachedConversation!.visibility = newVisibility;
      conversationProvider?.updateConversation(_cachedConversation!);
      notifyListeners();
    }
  }

  /// Unlinks the calendar event from the current conversation
  Future<bool> unlinkCalendarEvent() async {
    try {
      final success = await conv_api.unlinkCalendarEvent(conversation.id);
      if (success) {
        _updateLocalConversationWithCalendarEvent(null);
        notifyListeners();
        return true;
      }
      return false;
    } catch (e) {
      return false;
    }
  }

  /// Helper method to update the local conversation state with a calendar event
  void _updateLocalConversationWithCalendarEvent(CalendarEventLink? calendarEvent) {
    if (_cachedConversation != null) {
      final updatedConversation = ServerConversation(
        id: _cachedConversation!.id,
        createdAt: _cachedConversation!.createdAt,
        structured: _cachedConversation!.structured,
        startedAt: _cachedConversation!.startedAt,
        finishedAt: _cachedConversation!.finishedAt,
        transcriptSegments: _cachedConversation!.transcriptSegments,
        appResults: _cachedConversation!.appResults,
        suggestedSummarizationApps: _cachedConversation!.suggestedSummarizationApps,
        geolocation: _cachedConversation!.geolocation,
        photos: _cachedConversation!.photos,
        audioFiles: _cachedConversation!.audioFiles,
        discarded: _cachedConversation!.discarded,
        deleted: _cachedConversation!.deleted,
        source: _cachedConversation!.source,
        language: _cachedConversation!.language,
        externalIntegration: _cachedConversation!.externalIntegration,
        calendarEvent: calendarEvent,
        status: _cachedConversation!.status,
        isLocked: _cachedConversation!.isLocked,
        starred: _cachedConversation!.starred,
        folderId: _cachedConversation!.folderId,
        visibility: _cachedConversation!.visibility,
        captureGroup: _cachedConversation!.captureGroup,
      );
      _cachedConversation = updatedConversation;
      conversationProvider?.updateConversation(updatedConversation);
    }
    notifyListeners();
  }

  /// Auto-links the conversation to the best overlapping calendar event
  Future<CalendarEventLink?> autoLinkCalendarEvent() async {
    try {
      final calendarEvent = await conv_api.autoLinkCalendarEvent(conversation.id);
      if (calendarEvent != null) {
        _updateLocalConversationWithCalendarEvent(calendarEvent);
      }
      return calendarEvent;
    } catch (e) {
      debugPrint('Error auto-linking calendar event: $e');
      return null;
    }
  }

  /// Links the conversation to a specific calendar event by event ID
  Future<CalendarEventLink?> linkCalendarEvent(String eventId) async {
    try {
      final calendarEvent = await conv_api.linkCalendarEvent(conversation.id, eventId);
      if (calendarEvent != null) {
        _updateLocalConversationWithCalendarEvent(calendarEvent);
      }
      return calendarEvent;
    } catch (e) {
      debugPrint('Error linking calendar event: $e');
      return null;
    }
  }

  /// Lists Google Calendar events around the conversation time for the picker UI
  Future<List<CalendarEventLink>> listCalendarEventsForPicker() async {
    try {
      final conversationStart = conversation.startedAt ?? conversation.createdAt;
      final conversationEnd = conversation.finishedAt ?? conversationStart.add(const Duration(hours: 1));

      final timeMin = conversationStart.subtract(const Duration(hours: 2));
      final timeMax = conversationEnd.add(const Duration(hours: 2));

      return await listGoogleCalendarEvents(timeMin: timeMin, timeMax: timeMax, maxResults: 30);
    } catch (e) {
      debugPrint('Error listing calendar events: $e');
      return [];
    }
  }

  String? _preferredSummarizationAppId;

  String? get preferredSummarizationAppId => _preferredSummarizationAppId;

  Future<bool> setPreferredSummarizationApp(String appId) async {
    if (!await setPreferredSummarizationAppServer(appId)) return false;
    _preferredSummarizationAppId = appId;
    SharedPreferencesUtil().preferredSummarizationAppId = appId;
    notifyListeners();
    return true;
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

    return appProvider!.apps.firstWhereOrNull((app) => app.id == lastUsedId && app.worksWithMemories() && app.enabled);
  }

  bool _isDisposed = false;

  @override
  void dispose() {
    _isDisposed = true;
    super.dispose();
  }
}
