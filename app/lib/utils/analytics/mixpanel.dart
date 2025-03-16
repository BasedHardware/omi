import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/fact.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';
import 'package:mixpanel_flutter/mixpanel_flutter.dart';

class MixpanelManager {
  static final MixpanelManager _instance = MixpanelManager._internal();
  static Mixpanel? _mixpanel;
  static final SharedPreferencesUtil _preferences = SharedPreferencesUtil();

  static Future<void> init() async {
    if (Env.mixpanelProjectToken == null) return;
    if (_mixpanel == null) {
      _mixpanel = await Mixpanel.init(
        Env.mixpanelProjectToken!,
        optOutTrackingDefault: false,
        trackAutomaticEvents: true,
      );
      _mixpanel?.setLoggingEnabled(false);
    }
  }

  factory MixpanelManager() {
    return _instance;
  }

  MixpanelManager._internal();

  setPeopleValues() {
    setUserProperty('Notifications Enabled', _preferences.notificationsEnabled);
    setUserProperty('Location Enabled', _preferences.locationEnabled);
    setUserProperty('Apps Enabled Count', _preferences.enabledAppsCount);
    setUserProperty('Apps Integrations Enabled Count', _preferences.enabledAppsIntegrationsCount);
    setUserProperty('Speaker Profile', _preferences.hasSpeakerProfile);
    setUserProperty('Calendar Enabled', _preferences.calendarEnabled);
    setUserProperty('Recordings Language', _preferences.recordingsLanguage);
    setUserProperty('Authorized Storing Recordings', _preferences.permissionStoreRecordingsEnabled);
  }

  setUserProperty(String key, dynamic value) => _mixpanel?.getPeople().set(key, value);

  void optInTracking() {
    _mixpanel?.optInTracking();
    identify();
  }

  void optOutTracking() {
    _mixpanel?.optOutTracking();
    _mixpanel?.reset();
  }

  void identify() {
    _mixpanel?.identify(_preferences.uid);
    _instance.setPeopleValues();
    setNameAndEmail();
  }

  void migrateUser(String newUid) {
    _mixpanel?.alias(newUid, _preferences.uid);
    _mixpanel?.identify(newUid);
    setNameAndEmail();
  }

  void setNameAndEmail() {
    setUserProperty('\$name', SharedPreferencesUtil().fullName);
    setUserProperty('\$email', SharedPreferencesUtil().email);
  }

  void track(String eventName, {Map<String, dynamic>? properties}) =>
      _mixpanel?.track(eventName, properties: properties);

  void startTimingEvent(String eventName) => _mixpanel?.timeEvent(eventName);

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

  void factsPageCategoryOpened(FactCategory category) =>
      track('Fact Page Category Opened', properties: {'category': category.toString().split('.').last});

  void factsPageDeletedFact(Fact fact) => track(
        'Fact Page Deleted Fact',
        properties: {
          'fact_category': fact.category.toString().split('.').last,
        },
      );

  void factsPageEditedFact() => track('Fact Page Edited Fact');

  void factsPageCreateFactBtn() => track('Fact Page Create Fact Button Pressed');

  void factsPageCreatedFact(FactCategory category) =>
      track('Fact Page Created Fact', properties: {'fact_category': category.toString().split('.').last});

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
    properties['transcript_language'] = _preferences.recordingsLanguage;
    track('Memory Created', properties: properties);
  }

  void conversationListItemClicked(ServerConversation conversation, int idx) =>
      track('Memory List Item Clicked', properties: getConversationEventProperties(conversation));

  void conversationShareButtonClick(ServerConversation conversation) =>
      track('Memory Share Button Clicked', properties: getConversationEventProperties(conversation));

  void conversationDeleted(ServerConversation conversation) =>
      track('Memory Deleted', properties: getConversationEventProperties(conversation));

  void chatMessageSent(String message) => track('Chat Message Sent',
      properties: {'message_length': message.length, 'message_word_count': message.split(' ').length});

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

  void deleteUser() => _mixpanel?.getPeople().deleteUser();
}
