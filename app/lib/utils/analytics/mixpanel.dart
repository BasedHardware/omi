import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:mixpanel_flutter/mixpanel_flutter.dart';
import 'package:mixpanel_analytics/mixpanel_analytics.dart';

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
        if (PlatformService.isMobile) {
          // Use mixpanel_flutter for mobile platforms
          if (_mixpanel == null) {
            _mixpanel = await Mixpanel.init(
              Env.mixpanelProjectToken!,
              optOutTrackingDefault: false,
              trackAutomaticEvents: true,
            );
            _mixpanel?.setLoggingEnabled(false);
          }
        } else if (PlatformService.isDesktop) {
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
          if (PlatformService.isMobile) {
            _mixpanel?.getPeople().set(key, value);
          } else if (PlatformService.isDesktop) {
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
        if (PlatformService.isMobile) {
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
        if (PlatformService.isMobile) {
          _mixpanel?.optOutTracking();
          _mixpanel?.reset();
        } else if (PlatformService.isDesktop) {
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
        if (PlatformService.isMobile) {
          _mixpanel?.identify(_preferences.uid);
        } else if (PlatformService.isDesktop) {
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
        if (PlatformService.isMobile) {
          _mixpanel?.alias(newUid, _preferences.uid);
          _mixpanel?.identify(newUid);
        } else if (PlatformService.isDesktop) {
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
          if (PlatformService.isMobile) {
            _mixpanel?.track(eventName, properties: properties);
          } else if (PlatformService.isDesktop) {
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
          if (PlatformService.isMobile) {
            _mixpanel?.timeEvent(eventName);
          } else if (PlatformService.isDesktop) {
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

  void assignSheetOpened() => track('Assign Sheet Opened');

  void assignedSegment(String assignType) => track('Assigned Segment $assignType');

  void unassignedSegment() => track('Unassigned Segment');

  void deleteAccountClicked() => track('Delete Account Clicked');

  void deleteAccountConfirmed() => track('Delete Account Confirmed');

  void deleteAccountCancelled() => track('Delete Account Cancelled');

  void deleteUser() => PlatformService.executeIfSupported(
        PlatformService.isMixpanelSupported,
        () {
          if (PlatformService.isMobile) {
            _mixpanel?.getPeople().deleteUser();
          } else if (PlatformService.isDesktop) {
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
}
