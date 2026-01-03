import 'package:mixpanel_analytics/mixpanel_analytics.dart';
import 'package:mixpanel_flutter/mixpanel_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/platform/platform_service.dart';

class MixpanelManager {
  static final MixpanelManager _instance = MixpanelManager._internal();
  static Mixpanel? _mixpanel; // For mobile platforms
  static MixpanelAnalytics? _mixpanelAnalytics; // For desktop platforms
  static final SharedPreferencesUtil _preferences = SharedPreferencesUtil();

  static Future<void> init() async {
    if (Env.mixpanelProjectToken == null) return;
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isMixpanelSupported,
      () async {
        if (PlatformService.isMixpanelNativelySupported) {
          if (_mixpanel == null) {
            _mixpanel = await Mixpanel.init(
              Env.mixpanelProjectToken!,
              optOutTrackingDefault: false,
              trackAutomaticEvents: true,
            );
            _mixpanel?.setLoggingEnabled(false);
          }
        } else {
          // Use mixpanel_analytics for desktop platforms
          _mixpanelAnalytics ??= MixpanelAnalytics.batch(
            token: Env.mixpanelProjectToken!,
            uploadInterval: const Duration(seconds: 3),
            userId$: Stream.value(_preferences.uid),
            useIp: true,
            verbose: false,
          );
        }
      },
    );
  }

  factory MixpanelManager() {
    return _instance;
  }

  MixpanelManager._internal();

  setPeopleValues() {
    PlatformService.executeIfSupported(
      PlatformService.isMixpanelSupported,
      () {
        setUserProperty('Notifications Enabled', _preferences.notificationsEnabled);
        setUserProperty('Location Enabled', _preferences.locationEnabled);
        setUserProperty('Apps Enabled Count', _preferences.enabledAppsCount);
        setUserProperty('Apps Integrations Enabled Count', _preferences.enabledAppsIntegrationsCount);
        setUserProperty('Speaker Profile', _preferences.hasSpeakerProfile);
        setUserProperty('Calendar Enabled', _preferences.calendarEnabled);
        setUserProperty('Primary Language', _preferences.userPrimaryLanguage);
        setUserProperty('Authorized Storing Recordings', _preferences.permissionStoreRecordingsEnabled);
      },
    );
  }

  setUserProperty(String key, dynamic value) => PlatformService.executeIfSupported(
        PlatformService.isMixpanelSupported,
        () {
          if (PlatformService.isMixpanelNativelySupported) {
            _mixpanel?.getPeople().set(key, value);
          } else {
            _mixpanelAnalytics?.engage(
              operation: MixpanelUpdateOperations.$set,
              value: {key: value},
            );
          }
        },
      );

  void optInTracking() {
    PlatformService.executeIfSupported(
      PlatformService.isMixpanelSupported,
      () {
        if (PlatformService.isMixpanelNativelySupported) {
          _mixpanel?.optInTracking();
        }
        // Note: mixpanel_analytics doesn't have built-in opt-in/opt-out, but we can still identify
        identify();
      },
    );
  }

  void optOutTracking() {
    PlatformService.executeIfSupported(
      PlatformService.isMixpanelSupported,
      () {
        if (PlatformService.isMixpanelNativelySupported) {
          _mixpanel?.optOutTracking();
          _mixpanel?.reset();
        } else {
          // Note: mixpanel_analytics doesn't have built-in opt-out,
          // but we can set userId to null to stop tracking
          _mixpanelAnalytics?.userId = null;
        }
      },
    );
  }

  void identify() {
    PlatformService.executeIfSupported(
      PlatformService.isMixpanelSupported,
      () {
        if (PlatformService.isMixpanelNativelySupported) {
          _mixpanel?.identify(_preferences.uid);
        } else {
          _mixpanelAnalytics?.userId = _preferences.uid;
        }
        _instance.setPeopleValues();
        setNameAndEmail();
      },
    );
  }

  void migrateUser(String newUid) {
    PlatformService.executeIfSupported(
      PlatformService.isMixpanelSupported,
      () {
        if (PlatformService.isMixpanelNativelySupported) {
          _mixpanel?.alias(newUid, _preferences.uid);
          _mixpanel?.identify(newUid);
        } else {
          // Note: mixpanel_analytics doesn't have built-in alias,
          // but we can just set the new userId
          _mixpanelAnalytics?.userId = newUid;
        }
        setNameAndEmail();
      },
    );
  }

  void setNameAndEmail() {
    setUserProperty('\$name', SharedPreferencesUtil().fullName);
    setUserProperty('\$email', SharedPreferencesUtil().email);
  }

  void track(String eventName, {Map<String, dynamic>? properties}) => PlatformService.executeIfSupported(
        PlatformService.isMixpanelSupported,
        () {
          if (PlatformService.isMixpanelNativelySupported) {
            _mixpanel?.track(eventName, properties: properties);
          } else {
            _mixpanelAnalytics?.track(
              event: eventName,
              properties: properties ?? {},
            );
          }
        },
      );

  void startTimingEvent(String eventName) => PlatformService.executeIfSupported(
        PlatformService.isMixpanelSupported,
        () {
          if (PlatformService.isMixpanelNativelySupported) {
            _mixpanel?.timeEvent(eventName);
          } else {
            // Note: mixpanel_analytics doesn't have built-in timing events,
            // but we can track the start time manually in properties
            _mixpanelAnalytics?.track(
              event: eventName,
              properties: {'event_start_time': DateTime.now().millisecondsSinceEpoch},
            );
          }
        },
      );

  void onboardingDeviceConnected() => track('Onboarding Device Connected');

  void onboardingCompleted() => track('Onboarding Completed');

  void onboardingStepCompleted(String step) => track('Onboarding Step $step Completed');

  void settingsSaved({
    bool hasWebhookConversationCreated = false,
    bool hasWebhookTranscriptReceived = false,
  }) =>
      track('Developer Settings Saved', properties: {
        'has_webhook_memory_created': hasWebhookConversationCreated,
        'has_webhook_transcript_received': hasWebhookTranscriptReceived,
      });

  void pageOpened(String name) => track('$name Opened');

  void appEnabled(String appId) {
    track('App Enabled', properties: {'app_id': appId});
    setUserProperty('Apps Enabled Count', _preferences.enabledAppsCount);
  }

  void appPurchaseStarted(String appId) => track('App Purchase Started', properties: {'app_id': appId});

  void appPurchaseCompleted(String appId) => track('App Purchase Completed', properties: {'app_id': appId});

  void privateAppSubmitted(Map<String, dynamic> properties) => track('Private App Submitted', properties: properties);

  void publicAppSubmitted(Map<String, dynamic> properties) => track('Public App Submitted', properties: properties);

  void appDisabled(String appId) {
    track('App Disabled', properties: {'app_id': appId});
    setUserProperty('Apps Enabled Count', _preferences.enabledAppsCount);
  }

  void appRated(String appId, double rating) {
    track('App Rated', properties: {'app_id': appId, 'rating': rating});
  }

  void phoneMicRecordingStarted() => track('Phone Mic Recording Started');

  void phoneMicRecordingStopped() => track('Phone Mic Recording Stopped');

  void appResultExpanded(ServerConversation conversation, String appId) {
    track('App Result Expanded', properties: getConversationEventProperties(conversation)..['app_id'] = appId);
  }

  void languageChanged(String language) {
    track('App Language Changed', properties: {'language': language});
    setUserProperty('App Primary Language', language);
  }

  void recordingLanguageChanged(String language) {
    track('Recording Language Changed', properties: {'language': language});
    setUserProperty('Recordings Language', language);
  }

  void calendarEnabled() {
    track('Calendar Enabled');
    setUserProperty('Calendar Enabled', true);
  }

  void calendarDisabled() {
    track('Calendar Disabled');
    setUserProperty('Calendar Enabled', false);
  }

  void calendarModePressed(String mode) => track('Calendar Mode $mode Pressed');

  void calendarTypeChanged(String type) => track('Calendar Type Changed', properties: {'type': type});

  void calendarSelected() => track('Calendar Selected');

  void bottomNavigationTabClicked(String tab) => track('Bottom Navigation Tab Clicked', properties: {'tab': tab});

  void deviceConnected() => track('Device Connected', properties: {
        ..._preferences.btDevice.toJson(),
      });

  void deviceDisconnected() => track('Device Disconnected');

  void memoriesPageCategoryOpened(MemoryCategory category) =>
      track('Fact Page Category Opened', properties: {'category': category.toString().split('.').last});

  void memoriesPageDeletedMemory(Memory memory) => track(
        'Fact Page Deleted Fact',
        properties: {
          'fact_category': memory.category.toString().split('.').last,
        },
      );

  void memoriesPageEditedMemory() => track('Fact Page Edited Fact');

  void memoriesPageCreateMemoryBtn() => track('Fact Page Create Fact Button Pressed');

  void memoriesPageReviewBtn() => track('Fact page Review Button Pressed');

  void memoriesPageCreatedMemory(MemoryCategory category) =>
      track('Fact Page Created Fact', properties: {'fact_category': category.toString().split('.').last});

  void memorySearched(String query, int resultsCount) {
    track('Fact Searched', properties: {
      'search_query_length': query.length,
      'results_count': resultsCount,
    });
  }

  void memorySearchCleared(int totalFactsCount) {
    track('Fact Search Cleared', properties: {'total_facts_count': totalFactsCount});
  }

  void memoryListItemClicked(Memory memory) {
    track('Fact List Item Clicked', properties: {
      'fact_id': memory.id,
      'fact_category': memory.category.toString().split('.').last,
    });
  }

  void memoryVisibilityChanged(Memory memory, MemoryVisibility newVisibility) {
    track('Fact Visibility Changed', properties: {
      'fact_id': memory.id,
      'fact_category': memory.category.toString().split('.').last,
      'new_visibility': newVisibility.name,
    });
  }

  void memoriesAllVisibilityChanged(MemoryVisibility newVisibility, int count) {
    track('All Facts Visibility Changed', properties: {
      'new_visibility': newVisibility.name,
      'facts_count': count,
    });
  }

  void memoryReviewed(Memory memory, bool approved, String source) {
    track('Fact Reviewed', properties: {
      'fact_id': memory.id,
      'fact_category': memory.category.toString().split('.').last,
      'status': approved ? 'approved' : 'discarded',
      'source': source,
    });
  }

  void memoriesAllDeleted(int countBeforeDeletion) {
    track('All Facts Deleted', properties: {
      'facts_count_before_deletion': countBeforeDeletion,
    });
  }

  void memoriesFiltered(String filter) => track('Facts Filtered', properties: {'filter': filter});

  void memoriesManagementSheetOpened() => track('Facts Management Sheet Opened');

  Map<String, dynamic> _getTranscriptProperties(String transcript) {
    String transcriptCopy = transcript.substring(0, transcript.length);
    int speakersCount = 0;
    for (int i = 0; i < 5; i++) {
      if (transcriptCopy.contains('Speaker $i:')) speakersCount++;
      transcriptCopy = transcriptCopy.replaceAll('Speaker $i:', '');
    }
    transcriptCopy = transcriptCopy.replaceAll('  ', ' ').trim();
    return {
      'transcript_length': transcriptCopy.length,
      'transcript_word_count': transcriptCopy.split(' ').length,
      'speaker_count': speakersCount,
    };
  }

  Map<String, dynamic> getConversationEventProperties(ServerConversation convo) {
    var properties = _getTranscriptProperties(convo.getTranscript());
    int hoursAgo = DateTime.now().difference(convo.createdAt).inHours;
    properties['memory_hours_since_creation'] = hoursAgo;
    properties['memory_id'] = convo.id;
    properties['memory_discarded'] = convo.discarded;
    return properties;
  }

  void conversationCreated(ServerConversation conversation) {
    var properties = getConversationEventProperties(conversation);
    properties['memory_result'] = conversation.discarded ? 'discarded' : 'saved';
    properties['action_items_count'] = conversation.structured.actionItems.length;
    properties['transcript_language'] = _preferences.userPrimaryLanguage;

    // Additional properties for conversation creation
    properties['conversation_source'] = conversation.source?.toString().split('.').last ?? 'unknown';
    properties['duration_seconds'] = conversation.getDurationInSeconds();
    properties['timestamp'] = conversation.createdAt.toIso8601String();

    // Get the summarized app info if available
    if (conversation.appResults.isNotEmpty) {
      var summarizedApp = conversation.appResults.firstOrNull;
      if (summarizedApp != null && summarizedApp.appId != null) {
        properties['summary_app_id'] = summarizedApp.appId!;
      }
    }

    track('Memory Created', properties: properties);
  }

  void conversationListItemClicked(ServerConversation conversation, int idx) =>
      track('Memory List Item Clicked', properties: getConversationEventProperties(conversation));

  void conversationShareButtonClick(ServerConversation conversation) =>
      track('Memory Share Button Clicked', properties: getConversationEventProperties(conversation));

  void conversationDeleted(ServerConversation conversation) =>
      track('Memory Deleted', properties: getConversationEventProperties(conversation));

  void chatMessageSent({
    required String message,
    required bool includesFiles,
    required int numberOfFiles,
    required String chatTargetId,
    required bool isPersonaChat,
    required bool isVoiceInput,
  }) =>
      track('Chat Message Sent', properties: {
        'message_length': message.length,
        'message_word_count': message.split(' ').length,
        'includes_files': includesFiles,
        'number_of_files': numberOfFiles,
        'chat_target_id': chatTargetId,
        'is_persona_chat': isPersonaChat,
        'is_voice_input': isVoiceInput,
      });

  void chatVoiceInputUsed({required String chatTargetId, required bool isPersonaChat}) {
    track('Chat Voice Input Used', properties: {
      'chat_target_id': chatTargetId,
      'is_persona_chat': isPersonaChat,
    });
  }

  void speechProfileCapturePageClicked() => track('Speech Profile Capture Page Clicked');

  void showDiscardedMemoriesToggled(bool showDiscarded) =>
      track('Show Discarded Memories Toggled', properties: {'show_discarded': showDiscarded});

  // Conversation Display Settings Events
  void conversationDisplaySettingsOpened() => track('Conversation Display Settings Opened');

  void showShortConversationsToggled(bool showShort) =>
      track('Show Short Conversations Toggled', properties: {'show_short': showShort});

  void showDiscardedConversationsToggled(bool showDiscarded) =>
      track('Show Discarded Conversations Toggled', properties: {'show_discarded': showDiscarded});

  void shortConversationThresholdChanged(int thresholdSeconds) => track(
        'Short Conversation Threshold Changed',
        properties: {'threshold_seconds': thresholdSeconds, 'threshold_minutes': thresholdSeconds ~/ 60},
      );

  // Conversation Merge Events
  void conversationMergeSelectionModeEntered() => track('Conversation Merge Selection Mode Entered');

  void conversationMergeSelectionModeExited() => track('Conversation Merge Selection Mode Exited');

  void conversationSelectedForMerge(String conversationId, int totalSelected) => track(
        'Conversation Selected For Merge',
        properties: {'conversation_id': conversationId, 'total_selected': totalSelected},
      );

  void conversationMergeInitiated(List<String> conversationIds) => track(
        'Conversation Merge Initiated',
        properties: {'conversation_count': conversationIds.length, 'conversation_ids': conversationIds},
      );

  void conversationMergeCompleted(String mergedConversationId, List<String> removedConversationIds) => track(
        'Conversation Merge Completed',
        properties: {
          'merged_conversation_id': mergedConversationId,
          'removed_count': removedConversationIds.length,
          'removed_conversation_ids': removedConversationIds,
        },
      );

  void conversationMergeFailed(List<String> conversationIds) => track(
        'Conversation Merge Failed',
        properties: {'conversation_count': conversationIds.length, 'conversation_ids': conversationIds},
      );

  void chatMessageConversationClicked(ServerConversation conversation) =>
      track('Chat Message Memory Clicked', properties: getConversationEventProperties(conversation));

  void addManualConversationClicked() => track('Add Manual Memory Clicked');

  void manualConversationCreated(ServerConversation conversation) =>
      track('Manual Memory Created', properties: getConversationEventProperties(conversation));

  void setUserProperties(String whatDoYouDo, String whereDoYouPlanToUseYourFriend, String ageRange) {
    setUserProperty('What the user does', whatDoYouDo);
    setUserProperty('Using Omi At', whereDoYouPlanToUseYourFriend);
    setUserProperty('Age Range', ageRange);
  }

  void reProcessConversation(ServerConversation conversation) =>
      track('Re-process Memory', properties: getConversationEventProperties(conversation));

  void developerModeEnabled() {
    track('Developer Mode Enabled');
    setUserProperty('Dev Mode Enabled', true);
  }

  void developerModeDisabled() {
    track('Developer Mode Disabled');
    setUserProperty('Dev Mode Enabled', false);
  }

  void userIDCopied() => track('User ID Copied');

  void exportMemories() => track('Dev Mode Export Memories');

  void importMemories() => track('Dev Mode Import Memories');

  void importedMemories() => track('Dev Mode Imported Memories');

  void supportContacted() => track('Support Contacted');

  void copiedConversationDetails(ServerConversation conversation, {String source = ''}) =>
      track('Copied Memory Detail $source'.trim(), properties: getConversationEventProperties(conversation));

  void checkedActionItem(ServerConversation conversation, int idx) =>
      track('Checked Action Item', properties: getConversationEventProperties(conversation));

  void uncheckedActionItem(ServerConversation conversation, int idx) =>
      track('Unchecked Action Item', properties: getConversationEventProperties(conversation));

  void deletedActionItem(ServerConversation conversation) =>
      track('Deleted Action Item', properties: getConversationEventProperties(conversation));

  void paywallOpened(String source) => track('Paywall Opened', properties: {'source': source});

  void upgradePlanSelected({required String plan, required String source}) =>
      track('Upgrade Plan Selected', properties: {'plan': plan, 'source': source});

  void upgradeSucceeded() => track('Upgrade Succeeded');

  void upgradeCancelled() => track('Upgrade Cancelled');

  void upgradeModalDismissed() => track('Upgrade Modal Dismissed');

  void upgradeModalClicked() => track('Upgrade Modal Clicked');

  void getFriendClicked() => track('Get Friend Clicked');

  void connectFriendClicked() => track('Connect Friend Clicked');

  void disconnectFriendClicked() => track('Disconnect Friend Clicked');

  void batteryIndicatorClicked() => track('Battery Indicator Clicked');

  void useWithoutDeviceOnboardingWelcome() => track('Use Without Device Onboarding Welcome');

  void useWithoutDeviceOnboardingFindDevices() => track('Use Without Device Onboarding Find Devices');

  // void pageViewed(String pageName) => startTimingEvent('Page View $pageName');

  void addedPerson() => track('Added Person');

  void removedPerson() => track('Removed Person');

  void tagSheetOpened() => track('Tag Sheet Opened');

  void taggedSegment(String assignType) => track('Tagged Segment $assignType');

  void untaggedSegment() => track('Untagged Segment');

  void deleteAccountClicked() => track('Delete Account Clicked');

  void deleteAccountConfirmed() => track('Delete Account Confirmed');

  void deleteAccountCancelled() => track('Delete Account Cancelled');

  void deleteUser() => PlatformService.executeIfSupported(
        PlatformService.isMixpanelSupported,
        () {
          if (PlatformService.isMixpanelNativelySupported) {
            _mixpanel?.getPeople().deleteUser();
          } else {
            _mixpanelAnalytics?.engage(
              operation: MixpanelUpdateOperations.$delete,
              value: {},
            );
          }
        },
      );

  // Apps Filter
  void appsFilterOpened() => track('Apps Filter Opened');
  void appsFilterApplied() => track('Apps Filter Applied');
  void appsCategoryFilter(String category, bool isSelected) {
    track('Apps Category Filter', properties: {'category': category, 'selected': isSelected});
  }

  void appsTypeFilter(String type, bool isSelected) {
    track('Apps Type Filter', properties: {'type': type, 'selected': isSelected});
  }

  void appsSortFilter(String sortBy, bool isSelected) {
    track('Apps Sort Filter', properties: {'sort_by': sortBy, 'selected': isSelected});
  }

  void appsRatingFilter(String rating, bool isSelected) {
    track('Apps Rating Filter', properties: {'rating': rating, 'selected': isSelected});
  }

  void appsCapabilityFilter(String capability, bool isSelected) {
    track('Apps Capability Filter', properties: {'capability': capability, 'selected': isSelected});
  }

  void appsClearFilters() => track('Apps Clear Filters');

  // Persona Events
  void personaProfileViewed({String? personaId, required String source}) {
    track('Persona Profile Viewed', properties: {
      if (personaId != null) 'persona_id': personaId,
      'source': source,
    });
  }

  void personaCreateStarted() => track('Persona Create Started');

  void personaCreateImagePicked() => track('Persona Create Image Picked');

  void personaCreated({
    required String personaId,
    required bool isPublic,
    List<String>? connectedAccounts,
    bool? hasOmiConnection,
    bool? hasTwitterConnection,
  }) {
    track('Persona Created', properties: {
      'persona_id': personaId,
      'is_public': isPublic,
      if (connectedAccounts != null) 'connected_accounts': connectedAccounts,
      if (hasOmiConnection != null) 'has_omi_connection': hasOmiConnection,
      if (hasTwitterConnection != null) 'has_twitter_connection': hasTwitterConnection,
    });
  }

  void personaCreateFailed({String? errorMessage}) {
    track('Persona Create Failed', properties: {
      if (errorMessage != null) 'error_message': errorMessage,
    });
  }

  void personaUpdateStarted({required String personaId}) {
    track('Persona Update Started', properties: {'persona_id': personaId});
  }

  void personaUpdateImagePicked({required String personaId}) {
    track('Persona Update Image Picked', properties: {'persona_id': personaId});
  }

  void personaUpdated({
    required String personaId,
    List<String>? updatedFields,
    required bool isPublic,
    List<String>? connectedAccounts,
    bool? hasOmiConnection,
    bool? hasTwitterConnection,
  }) {
    track('Persona Updated', properties: {
      'persona_id': personaId,
      if (updatedFields != null && updatedFields.isNotEmpty) 'updated_fields': updatedFields,
      'is_public': isPublic,
      if (connectedAccounts != null) 'connected_accounts': connectedAccounts,
      if (hasOmiConnection != null) 'has_omi_connection': hasOmiConnection,
      if (hasTwitterConnection != null) 'has_twitter_connection': hasTwitterConnection,
    });
  }

  void personaUpdateFailed({required String personaId, String? errorMessage}) {
    track('Persona Update Failed', properties: {
      'persona_id': personaId,
      if (errorMessage != null) 'error_message': errorMessage,
    });
  }

  void personaPublicToggled({required String personaId, required bool isPublic}) {
    track('Persona Public Toggled', properties: {
      'persona_id': personaId,
      'is_public': isPublic,
    });
  }

  void personaOmiConnectionToggled({required String personaId, required bool omiConnected}) {
    track('Persona OMI Connection Toggled', properties: {
      'persona_id': personaId,
      'omi_connected': omiConnected,
    });
  }

  void personaTwitterConnectionToggled({required String personaId, required bool twitterConnected}) {
    track('Persona Twitter Connection Toggled', properties: {
      'persona_id': personaId,
      'twitter_connected': twitterConnected,
    });
  }

  void personaTwitterProfileFetched({required String twitterHandle, required bool fetchSuccessful}) {
    track('Persona Twitter Profile Fetched', properties: {
      'twitter_handle': twitterHandle,
      'fetch_successful': fetchSuccessful,
    });
  }

  void personaTwitterOwnershipVerified({
    String? personaId,
    required String twitterHandle,
    required bool verificationSuccessful,
  }) {
    track('Persona Twitter Ownership Verified', properties: {
      if (personaId != null) 'persona_id': personaId,
      'twitter_handle': twitterHandle,
      'verification_successful': verificationSuccessful,
    });
  }

  void personaShared({required String? personaId, required String? personaUsername}) {
    track('Persona Shared', properties: {
      if (personaId != null) 'persona_id': personaId,
      if (personaUsername != null) 'persona_username': personaUsername,
    });
  }

  void personaUsernameCheck({required String username, required bool isTaken}) {
    track('Persona Username Check', properties: {
      'username': username,
      'is_taken': isTaken,
    });
  }

  void personaEnabled({required String personaId}) {
    track('Persona Enabled', properties: {'persona_id': personaId});
  }

  void personaEnableFailed({required String personaId, String? errorMessage}) {
    track('Persona Enable Failed', properties: {
      'persona_id': personaId,
      if (errorMessage != null) 'error_message': errorMessage,
    });
  }

  // Brain Map Events
  void brainMapOpened() => track('Brain Map Opened');

  void brainMapNodeClicked(String nodeId, String label, String type) {
    track('Brain Map Node Clicked', properties: {
      'node_id': nodeId,
      'label': label,
      'type': type,
    });
  }

  void brainMapShareClicked() => track('Brain Map Share Clicked');

  void brainMapRebuilt() => track('Brain Map Rebuilt');

  // Summarized Apps Sheet Events
  void summarizedAppSheetViewed({
    required String conversationId,
    String? currentSummarizedAppId,
  }) {
    track('Summarized App Sheet Viewed', properties: {
      'conversation_id': conversationId,
      'current_summarized_app_id': currentSummarizedAppId ?? 'auto',
    });
  }

  void summarizedAppSelected({
    required String conversationId,
    required String selectedAppId,
    String? previousAppId,
  }) {
    track('Summarized App Selected', properties: {
      'conversation_id': conversationId,
      'selected_app_id': selectedAppId,
      'previous_app_id': previousAppId ?? 'auto',
    });
  }

  void summarizedAppEnableAppsClicked({required String conversationId}) {
    track('Summarized App Enable Apps Clicked', properties: {
      'conversation_id': conversationId,
    });
  }

  void summarizedAppCreateTemplateClicked({required String conversationId}) {
    track('Summarized App Create Template Clicked', properties: {
      'conversation_id': conversationId,
    });
  }

  void quickTemplateCreated({
    required String conversationId,
    required String appName,
    required bool isPublic,
  }) {
    track('Quick Template Created', properties: {
      'conversation_id': conversationId,
      'app_name': appName,
      'is_public': isPublic,
    });
  }

  // Action Items Page Events
  void actionItemsPageOpened() => track('Action Items Page Opened');

  void actionItemsViewToggled(bool isGroupedView) {
    track('Action Items View Toggled', properties: {'grouped_view': isGroupedView});
  }

  void actionItemToggledCompletionOnActionItemsPage({
    required String conversationId,
    required String actionItemDescription, // Using description as a pseudo-ID if no stable ID exists
    required bool isCompleted,
  }) {
    track('Action Item Completion Toggled on Action Items Page', properties: {
      'conversation_id': conversationId,
      'action_item_description': actionItemDescription,
      'is_completed': isCompleted,
    });
  }

  void actionItemTappedForEditOnActionItemsPage({
    required String conversationId,
    required String actionItemDescription,
  }) {
    track('Action Item Tapped for Edit on Action Items Page', properties: {
      'conversation_id': conversationId,
      'action_item_description': actionItemDescription,
    });
  }

  void actionItemsDateFilterApplied(String filterType) {
    track('Action Items Date Filter Applied', properties: {
      'filter_type': filterType,
    });
  }

  void actionItemsDateFilterCleared() {
    track('Action Items Date Filter Cleared');
  }

  void actionItemTabChanged(String tabName) {
    track('Action Item Tab Changed', properties: {
      'tab_name': tabName,
    });
  }

  void actionItemCompleted({required String fromTab}) {
    track('Action Item Completed', properties: {
      'from_tab': fromTab,
    });
  }

  void trainingDataOptInSubmitted() {
    track('Training Data Opt-In Submitted');
    setUserProperty('Training Data Opted In', true);
  }

  void trainingDataOptInApproved() {
    track('Training Data Opt-In Approved');
    setUserProperty('Training Data Status', 'approved');
  }

  // Homepage Events
  void recordingMuteToggled({required bool isMuted, required String recordingType}) {
    track('Recording Mute Toggled', properties: {
      'is_muted': isMuted,
      'recording_type': recordingType,
    });
  }

  void deletedConversationsFilterToggled(bool showDeleted) {
    track('Deleted Conversations Filter Toggled', properties: {'show_deleted': showDeleted});
  }

  void calendarFilterApplied(DateTime selectedDate) {
    track('Calendar Filter Applied', properties: {
      'selected_date': selectedDate.toIso8601String(),
      'days_ago': DateTime.now().difference(selectedDate).inDays,
    });
  }

  void calendarFilterCleared() {
    track('Calendar Filter Cleared');
  }

  void searchBarFocused() {
    track('Search Bar Focused');
  }

  void searchQueryEntered(String query, int resultsCount) {
    track('Search Query Entered', properties: {
      'query_length': query.length,
      'query_word_count': query.split(' ').length,
      'results_count': resultsCount,
    });
  }

  void searchQueryCleared() {
    track('Search Query Cleared');
  }

  void conversationOpenedFromSearch({
    required ServerConversation conversation,
    required String searchQuery,
    required int conversationIndexInResults,
  }) {
    var properties = getConversationEventProperties(conversation);
    properties['search_query'] = searchQuery;
    properties['search_query_length'] = searchQuery.length;
    properties['conversation_index_in_results'] = conversationIndexInResults;
    track('Conversation Opened From Search', properties: properties);
  }

  void liveTranscriptCardClicked({
    required bool hasSegments,
    required bool hasPhotos,
    required int segmentCount,
    required int photoCount,
  }) {
    track('Live Transcript Card Clicked', properties: {
      'has_segments': hasSegments,
      'has_photos': hasPhotos,
      'segment_count': segmentCount,
      'photo_count': photoCount,
    });
  }

  void deviceInfoButtonClicked({String? deviceId, String? deviceName, int? batteryLevel}) {
    track('Device Info Button Clicked', properties: {
      if (deviceId != null) 'device_id': deviceId,
      if (deviceName != null) 'device_name': deviceName,
      if (batteryLevel != null) 'battery_level': batteryLevel,
    });
  }

  void conversationListItemClickedWithTimeDifference({
    required ServerConversation conversation,
    required int conversationIndex,
    required int hoursSinceConversation,
  }) {
    var properties = getConversationEventProperties(conversation);
    properties['conversation_index'] = conversationIndex;
    properties['hours_since_conversation'] = hoursSinceConversation;
    track('Conversation List Item Clicked', properties: properties);
  }

  void conversationSwipedToDelete(ServerConversation conversation) {
    var properties = getConversationEventProperties(conversation);
    track('Conversation Swiped To Delete', properties: properties);
  }

  // Conversation Detail Page Events
  void conversationDetailTabChanged(String tabName) {
    track('Conversation Detail Tab Changed', properties: {'tab_name': tabName});
  }

  void speakerEdited({
    required String conversationId,
    required int oldSpeakerCount,
    required int newSpeakerCount,
  }) {
    track('Speaker Edited', properties: {
      'conversation_id': conversationId,
      'old_speaker_count': oldSpeakerCount,
      'new_speaker_count': newSpeakerCount,
      'speaker_count_changed': oldSpeakerCount != newSpeakerCount,
    });
  }

  void conversationDetailSearchClicked({required String conversationId}) {
    track('Conversation Detail Search Clicked', properties: {
      'conversation_id': conversationId,
    });
  }

  void conversationDetailSearchQueryEntered({
    required String conversationId,
    required String query,
    required int resultsCount,
    required String activeTab,
  }) {
    track('Conversation Detail Search Query Entered', properties: {
      'conversation_id': conversationId,
      'query_length': query.length,
      'results_count': resultsCount,
      'active_tab': activeTab,
    });
  }

  void conversationReprocessedWithApp({
    required String conversationId,
    required String appId,
    required String appName,
    required bool isOwnApp,
    required bool wasAutoSelected,
  }) {
    track('Conversation Reprocessed', properties: {
      'conversation_id': conversationId,
      'app_id': appId,
      'app_name': appName,
      'is_own_app': isOwnApp,
      'was_auto_selected': wasAutoSelected,
    });
  }

  void conversationShared({
    required ServerConversation conversation,
    required String shareMethod,
  }) {
    var properties = getConversationEventProperties(conversation);
    properties['share_method'] = shareMethod;
    track('Conversation Shared', properties: properties);
  }

  void conversationThreeDotsMenuOpened({required String conversationId}) {
    track('Conversation Three Dots Menu Opened', properties: {
      'conversation_id': conversationId,
    });
  }

  void conversationThreeDotsMenuActionSelected({
    required String conversationId,
    required String action,
  }) {
    track('Conversation Three Dots Menu Action Selected', properties: {
      'conversation_id': conversationId,
      'action': action,
    });
  }

  // ============================================================================
  // ACTION ITEMS TRACKING
  // ============================================================================

  void actionItemChecked({
    required String actionItemId,
    required bool completed,
    required DateTime timestamp,
  }) {
    track('Action Item Checked', properties: {
      'action_item_id': actionItemId,
      'completed': completed,
      'timestamp': timestamp.toIso8601String(),
    });
  }

  void exportTasksBannerClicked() {
    track('Export Tasks Banner Clicked');
  }

  void taskIntegrationEnabled({
    required String appName,
    required bool success,
  }) {
    track('Task Integration Enabled', properties: {
      'app_name': appName,
      'success': success,
    });
  }

  void taskIntegrationAuthFailed({
    required String appName,
  }) {
    track('Task Integration Auth Failed', properties: {
      'app_name': appName,
    });
  }

  void taskIntegrationSettingsOpened({
    required String appName,
  }) {
    track('Task Integration Settings Opened', properties: {
      'app_name': appName,
    });
  }

  // ============================================================================
  // TRANSCRIPTION / CUSTOM STT TRACKING
  // ============================================================================

  void transcriptionSourceSelected({
    required String source, // 'omi' or 'custom'
  }) {
    track('Transcription Source Selected', properties: {
      'source': source,
    });
  }

  void transcriptionProviderSelected({
    required String provider, // e.g. 'openai', 'deepgram', 'gemini', 'local_whisper', 'custom', 'custom_live'
  }) {
    track('Transcription Provider Selected', properties: {
      'provider': provider,
    });
  }

  // ============================================================================
  // AUDIO PLAYBACK TRACKING
  // ============================================================================

  void audioPlaybackStarted({
    required String conversationId,
    int? durationSeconds,
  }) {
    track('Audio Playback Started', properties: {
      'conversation_id': conversationId,
      if (durationSeconds != null) 'duration_seconds': durationSeconds,
    });
  }

  void audioPlaybackPaused({
    required String conversationId,
    required int positionSeconds,
    int? durationSeconds,
  }) {
    track('Audio Playback Paused', properties: {
      'conversation_id': conversationId,
      'position_seconds': positionSeconds,
      if (durationSeconds != null) 'duration_seconds': durationSeconds,
      if (durationSeconds != null && durationSeconds > 0)
        'completion_percentage': ((positionSeconds / durationSeconds) * 100).round(),
    });
  }

  void audioPlaybackSeeked({
    required String conversationId,
    required int toPositionSeconds,
  }) {
    track('Audio Playback Seeked', properties: {
      'conversation_id': conversationId,
      'to_position_seconds': toPositionSeconds,
    });
  }

  void actionItemExported({
    required String actionItemId,
    required String appName,
    required DateTime timestamp,
  }) {
    track('Action Item Exported', properties: {
      'action_item_id': actionItemId,
      'app_name': appName,
      'timestamp': timestamp.toIso8601String(),
    });
  }

  void actionItemManuallyAdded({
    required String actionItemId,
    required DateTime timestamp,
  }) {
    track('Action Item Manually Added', properties: {
      'action_item_id': actionItemId,
      'timestamp': timestamp.toIso8601String(),
    });
  }

  void actionItemEdited({
    required String actionItemId,
    required bool titleChanged,
    required bool dateChanged,
  }) {
    track('Action Item Edited', properties: {
      'action_item_id': actionItemId,
      'title_changed': titleChanged,
      'date_changed': dateChanged,
    });
  }

  // ============================================================================
  // SETTINGS PAGE TRACKING
  // ============================================================================

  void settingsPageOpened({
    required String pageName,
  }) {
    track('Settings Page Opened', properties: {
      'page_name': pageName,
    });
  }

  void usageTabChanged({
    required String tabName,
  }) {
    track('Usage Tab Changed', properties: {
      'tab_name': tabName,
    });
  }

  // ============================================================================
  // APPS PAGE TRACKING
  // ============================================================================

  void appsSearched({
    required String searchTerm,
    required int resultCount,
  }) {
    track('Apps Searched', properties: {
      'search_term': searchTerm,
      'result_count': resultCount,
    });
  }

  void appsFilterMyApps({
    required bool enabled,
  }) {
    track('Apps Filter My Apps', properties: {
      'enabled': enabled,
    });
  }

  void appsFilterInstalled({
    required bool enabled,
  }) {
    track('Apps Filter Installed', properties: {
      'enabled': enabled,
    });
  }

  void appsFilterRating({
    required int rating,
  }) {
    track('Apps Filter Rating', properties: {
      'rating': rating,
    });
  }

  void appsFilterCategory({
    required String category,
  }) {
    track('Apps Filter Category', properties: {
      'category': category,
    });
  }

  void appsSortChanged({
    required String sortOption,
  }) {
    track('Apps Sort Changed', properties: {
      'sort_option': sortOption,
    });
  }

  void appsFilterCapability({
    required String capability,
  }) {
    track('Apps Filter Capability', properties: {
      'capability': capability,
    });
  }

  void appsCategoryPageOpened({
    required String category,
    required int appCount,
  }) {
    track('Apps Category Page Opened', properties: {
      'category': category,
      'app_count': appCount,
    });
  }

  // ============================================================================
  // APP DETAIL PAGE TRACKING
  // ============================================================================

  void appDetailViewed({
    required String appId,
    required String appName,
    String? category,
    double? rating,
    int? installs,
    bool? isInstalled,
  }) {
    track('App Detail Viewed', properties: {
      'app_id': appId,
      'app_name': appName,
      if (category != null) 'category': category,
      if (rating != null) 'rating': rating,
      if (installs != null) 'installs': installs,
      if (isInstalled != null) 'is_installed': isInstalled,
    });
  }

  void appDetailSectionViewed({
    required String appId,
    required String sectionName,
  }) {
    track('App Detail Section Viewed', properties: {
      'app_id': appId,
      'section_name': sectionName,
    });
  }

  void appDetailShared({
    required String appId,
    required String appName,
  }) {
    track('App Detail Shared', properties: {
      'app_id': appId,
      'app_name': appName,
    });
  }

  void appDetailReviewsOpened({
    required String appId,
    required int reviewCount,
  }) {
    track('App Detail Reviews Opened', properties: {
      'app_id': appId,
      'review_count': reviewCount,
    });
  }

  void appDetailReviewAdded({
    required String appId,
    required int rating,
    required bool hasComment,
  }) {
    track('App Detail Review Added', properties: {
      'app_id': appId,
      'rating': rating,
      'has_comment': hasComment,
    });
  }

  void appDetailSettingsOpened({
    required String appId,
  }) {
    track('App Detail Settings Opened', properties: {
      'app_id': appId,
    });
  }

  void appDetailSubscribeClicked({
    required String appId,
    required String appName,
    double? price,
  }) {
    track('App Detail Subscribe Clicked', properties: {
      'app_id': appId,
      'app_name': appName,
      if (price != null) 'price': price,
    });
  }

  void appDetailSubscriptionCancelled({
    required String appId,
    required String appName,
  }) {
    track('App Detail Subscription Cancelled', properties: {
      'app_id': appId,
      'app_name': appName,
    });
  }

  void appDetailPreviewImageViewed({
    required String appId,
    required int imageIndex,
  }) {
    track('App Detail Preview Image Viewed', properties: {
      'app_id': appId,
      'image_index': imageIndex,
    });
  }

  void appDetailChatClicked({
    required String appId,
    required String appName,
  }) {
    track('App Detail Chat Clicked', properties: {
      'app_id': appId,
      'app_name': appName,
    });
  }

  // ============================================================================
  // FOLDER TRACKING
  // ============================================================================

  void folderCreated({
    required String folderId,
    required String folderName,
    required String icon,
    required String color,
  }) {
    track('Folder Created', properties: {
      'folder_id': folderId,
      'folder_name': folderName,
      'icon': icon,
      'color': color,
    });
  }

  void folderUpdated({
    required String folderId,
    required String folderName,
  }) {
    track('Folder Updated', properties: {
      'folder_id': folderId,
      'folder_name': folderName,
    });
  }

  void folderDeleted({
    required String folderId,
    required String folderName,
    required int conversationCount,
    String? moveToFolderId,
  }) {
    track('Folder Deleted', properties: {
      'folder_id': folderId,
      'folder_name': folderName,
      'conversation_count': conversationCount,
      if (moveToFolderId != null) 'move_to_folder_id': moveToFolderId,
      'moved_conversations': moveToFolderId != null,
    });
  }

  void folderSelected({
    String? folderId,
    String? folderName,
  }) {
    track('Folder Selected', properties: {
      if (folderId != null) 'folder_id': folderId,
      if (folderName != null) 'folder_name': folderName,
      'is_all_tab': folderId == null,
    });
  }

  void folderContextMenuOpened({
    required String folderId,
    required String folderName,
  }) {
    track('Folder Context Menu Opened', properties: {
      'folder_id': folderId,
      'folder_name': folderName,
    });
  }

  void createFolderButtonClicked() {
    track('Create Folder Button Clicked');
  }

  void conversationDetailFolderChipClicked({
    required String conversationId,
    String? currentFolderId,
  }) {
    track('Conversation Detail Folder Chip Clicked', properties: {
      'conversation_id': conversationId,
      if (currentFolderId != null) 'current_folder_id': currentFolderId,
      'has_folder': currentFolderId != null,
    });
  }

  void conversationMovedToFolder({
    required String conversationId,
    String? fromFolderId,
    String? toFolderId,
    required String source,
  }) {
    track('Conversation Moved To Folder', properties: {
      'conversation_id': conversationId,
      if (fromFolderId != null) 'from_folder_id': fromFolderId,
      if (toFolderId != null) 'to_folder_id': toFolderId,
      'source': source,
      'was_in_folder': fromFolderId != null,
    });
  }

  void starredFilterToggled({
    required bool enabled,
    String? selectedFolderId,
  }) {
    track('Starred Filter Toggled', properties: {
      'enabled': enabled,
      if (selectedFolderId != null) 'selected_folder_id': selectedFolderId,
      'has_folder_filter': selectedFolderId != null,
    });
  }

  void conversationStarToggled({
    required ServerConversation conversation,
    required bool starred,
    required String source,
  }) {
    var properties = getConversationEventProperties(conversation);
    properties['starred'] = starred;
    properties['source'] = source;
    properties['duration_seconds'] = conversation.getDurationInSeconds();

    // Get the summarized app id if available
    if (conversation.appResults.isNotEmpty) {
      var summarizedApp = conversation.appResults.firstOrNull;
      if (summarizedApp != null && summarizedApp.appId != null) {
        properties['summary_app_id'] = summarizedApp.appId!;
      }
    }

    track('Conversation Star Toggled', properties: properties);
  }

  void omiDoubleTap({
    required String feature,
    Map<String, dynamic>? additionalProperties,
  }) {
    track('Omi Double Tap', properties: {
      'feature': feature,
      if (additionalProperties != null) ...additionalProperties,
    });
  }

  // ============================================================================
  // WRAPPED 2025 TRACKING
  // ============================================================================

  void wrappedPageOpened() {
    track('Wrapped Page Opened');
  }

  void wrappedBannerClicked() {
    track('Wrapped Banner Clicked');
  }

  void wrappedGenerationStarted() {
    track('Wrapped Generation Started');
    startTimingEvent('Wrapped Generation Completed');
  }

  void wrappedGenerationCompleted({
    required int totalConversations,
    required int totalMinutes,
    required int daysActive,
  }) {
    track('Wrapped Generation Completed', properties: {
      'total_conversations': totalConversations,
      'total_minutes': totalMinutes,
      'days_active': daysActive,
    });
  }

  void wrappedGenerationFailed({String? error}) {
    track('Wrapped Generation Failed', properties: {
      if (error != null) 'error': error,
    });
  }

  void wrappedCardViewed({
    required String cardName,
    required int cardIndex,
  }) {
    track('Wrapped Card Viewed', properties: {
      'card_name': cardName,
      'card_index': cardIndex,
    });
  }

  void wrappedShareButtonClicked({
    required String cardName,
    required int cardIndex,
  }) {
    track('Wrapped Share Button Clicked', properties: {
      'card_name': cardName,
      'card_index': cardIndex,
    });
    startTimingEvent('Wrapped Shared Successfully');
  }

  void wrappedSharedSuccessfully({
    required String cardName,
    required int cardIndex,
    int? fileSizeBytes,
  }) {
    track('Wrapped Shared Successfully', properties: {
      'card_name': cardName,
      'card_index': cardIndex,
      if (fileSizeBytes != null) 'file_size_bytes': fileSizeBytes,
      if (fileSizeBytes != null) 'file_size_kb': (fileSizeBytes / 1024).round(),
      if (fileSizeBytes != null) 'file_size_mb': (fileSizeBytes / (1024 * 1024)).toStringAsFixed(2),
    });
  }

  void wrappedShareFailed({
    required String cardName,
    required int cardIndex,
    String? error,
  }) {
    track('Wrapped Share Failed', properties: {
      'card_name': cardName,
      'card_index': cardIndex,
      if (error != null) 'error': error,
    });
  }

  // ============================================================================
  // DAILY SUMMARY / RECAP TRACKING
  // ============================================================================

  void dailySummarySettingsOpened() => track('Daily Summary Settings Opened');

  void dailySummaryToggled({required bool enabled}) {
    track('Daily Summary Toggled', properties: {'enabled': enabled});
    setUserProperty('Daily Summary Enabled', enabled);
  }

  void dailySummaryTimeChanged({required int hour}) {
    final hour12 = hour == 0 ? 12 : (hour > 12 ? hour - 12 : hour);
    final period = hour >= 12 ? 'PM' : 'AM';
    track('Daily Summary Time Changed', properties: {
      'hour_24': hour,
      'hour_12': hour12,
      'period': period,
      'display_time': '$hour12:00 $period',
    });
    setUserProperty('Daily Summary Hour', hour);
  }

  void dailySummaryDetailViewed({
    required String summaryId,
    required String date,
    String? source,
  }) {
    track('Daily Summary Detail Viewed', properties: {
      'summary_id': summaryId,
      'date': date,
      if (source != null) 'source': source,
    });
  }

  void dailySummaryTestGenerated({required String date}) {
    track('Daily Summary Test Generated', properties: {'date': date});
  }

  void dailySummaryTestGenerationFailed({required String date, String? error}) {
    track('Daily Summary Test Generation Failed', properties: {
      'date': date,
      if (error != null) 'error': error,
    });
  }

  void recapTabOpened() => track('Recap Tab Opened');

  void recapSummaryCardClicked({
    required String summaryId,
    required String date,
    required int cardIndex,
  }) {
    track('Recap Summary Card Clicked', properties: {
      'summary_id': summaryId,
      'date': date,
      'card_index': cardIndex,
    });
  }

  void dailySummaryNotificationReceived({
    required String summaryId,
    required String date,
  }) {
    track('Daily Summary Notification Received', properties: {
      'summary_id': summaryId,
      'date': date,
    });
  }

  void dailySummaryNotificationOpened({
    required String summaryId,
    required String date,
  }) {
    track('Daily Summary Notification Opened', properties: {
      'summary_id': summaryId,
      'date': date,
    });
  }

  void dailySummaryConversationClicked({
    required String summaryId,
    required String conversationId,
    required String source,
  }) {
    track('Daily Summary Conversation Clicked', properties: {
      'summary_id': summaryId,
      'conversation_id': conversationId,
      'source': source,
    });
  }

  void dailySummarySectionViewed({
    required String summaryId,
    required String sectionName,
  }) {
    track('Daily Summary Section Viewed', properties: {
      'summary_id': summaryId,
      'section_name': sectionName,
    });
  }
}
