import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/fact.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/env/env.dart';
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
    setUserProperty('Plugins Enabled Count', _preferences.enabledPluginsCount);
    setUserProperty('Plugins Integrations Enabled Count', _preferences.enabledPluginsIntegrationsCount);
    setUserProperty('Speaker Profile', _preferences.hasSpeakerProfile);
    setUserProperty('Calendar Enabled', _preferences.calendarEnabled);
    setUserProperty('Recordings Language', _preferences.recordingsLanguage);
    setUserProperty('Authorized Storing Recordings', _preferences.permissionStoreRecordingsEnabled);
    setUserProperty(
      'GCP Integration Set',
      _preferences.gcpCredentials.isNotEmpty && _preferences.gcpBucketName.isNotEmpty,
    );
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
    bool hasGCPCredentials = false,
    bool hasGCPBucketName = false,
    bool hasWebhookMemoryCreated = false,
    bool hasWebhookTranscriptReceived = false,
  }) =>
      track('Developer Settings Saved', properties: {
        'has_gcp_credentials': hasGCPCredentials,
        'has_gcp_bucket_name': hasGCPBucketName,
        'has_webhook_memory_created': hasWebhookMemoryCreated,
        'has_webhook_transcript_received': hasWebhookTranscriptReceived,
      });

  void pageOpened(String name) => track('$name Opened');

  void pluginEnabled(String pluginId) {
    track('Plugin Enabled', properties: {'plugin_id': pluginId});
    setUserProperty('Plugins Enabled Count', _preferences.enabledPluginsCount);
  }

  void pluginDisabled(String pluginId) {
    track('Plugin Disabled', properties: {'plugin_id': pluginId});
    setUserProperty('Plugins Enabled Count', _preferences.enabledPluginsCount);
  }

  void pluginRated(String pluginId, double rating) {
    track('Plugin Rated', properties: {'plugin_id': pluginId, 'rating': rating});
  }

  void phoneMicRecordingStarted() => track('Phone Mic Recording Started');

  void phoneMicRecordingStopped() => track('Phone Mic Recording Stopped');

  void pluginResultExpanded(ServerMemory memory, String pluginId) {
    track('Plugin Result Expanded', properties: getMemoryEventProperties(memory)..['plugin_id'] = pluginId);
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

  void calendarTypeChanged(String type) => track('Calendar Type Changed', properties: {'type': type});

  void calendarSelected() => track('Calendar Selected');

  void bottomNavigationTabClicked(String tab) => track('Bottom Navigation Tab Clicked', properties: {'tab': tab});

  void deviceConnected() => track('Device Connected');

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

  Map<String, dynamic> getMemoryEventProperties(ServerMemory memory) {
    var properties = _getTranscriptProperties(memory.getTranscript());
    int hoursAgo = DateTime.now().difference(memory.createdAt).inHours;
    properties['memory_hours_since_creation'] = hoursAgo;
    properties['memory_id'] = memory.id;
    properties['memory_discarded'] = memory.discarded;
    return properties;
  }

  void memoryCreated(ServerMemory memory) {
    var properties = getMemoryEventProperties(memory);
    properties['memory_result'] = memory.discarded ? 'discarded' : 'saved';
    properties['action_items_count'] = memory.structured.actionItems.length;
    properties['transcript_language'] = _preferences.recordingsLanguage;
    track('Memory Created', properties: properties);
  }

  void memoryListItemClicked(ServerMemory memory, int idx) =>
      track('Memory List Item Clicked', properties: getMemoryEventProperties(memory));

  void memoryShareButtonClick(ServerMemory memory) =>
      track('Memory Share Button Clicked', properties: getMemoryEventProperties(memory));

  void memoryDeleted(ServerMemory memory) => track('Memory Deleted', properties: getMemoryEventProperties(memory));

  void chatMessageSent(String message) => track('Chat Message Sent',
      properties: {'message_length': message.length, 'message_word_count': message.split(' ').length});

  void speechProfileCapturePageClicked() => track('Speech Profile Capture Page Clicked');

  void showDiscardedMemoriesToggled(bool showDiscarded) =>
      track('Show Discarded Memories Toggled', properties: {'show_discarded': showDiscarded});

  void chatMessageMemoryClicked(ServerMemory memory) =>
      track('Chat Message Memory Clicked', properties: getMemoryEventProperties(memory));

  void addManualMemoryClicked() => track('Add Manual Memory Clicked');

  void manualMemoryCreated(ServerMemory memory) =>
      track('Manual Memory Created', properties: getMemoryEventProperties(memory));

  void setUserProperties(String whatDoYouDo, String whereDoYouPlanToUseYourFriend, String ageRange) {
    setUserProperty('What the user does', whatDoYouDo);
    setUserProperty('Using Friend At', whereDoYouPlanToUseYourFriend);
    setUserProperty('Age Range', ageRange);
  }

  void reProcessMemory(ServerMemory memory) => track('Re-process Memory', properties: getMemoryEventProperties(memory));

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

  void copiedMemoryDetails(ServerMemory memory, {String source = ''}) =>
      track('Copied Memory Detail $source'.trim(), properties: getMemoryEventProperties(memory));

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
}
