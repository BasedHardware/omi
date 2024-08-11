import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/preferences.dart';
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
    setUserProperty('Dev Mode Enabled', _preferences.devModeEnabled);
    // setUserProperty('Plugins Enabled Count', _preferences.pluginsEnabled.length);
    setUserProperty('Speaker Profile', _preferences.hasSpeakerProfile);
    setUserProperty('Calendar Enabled', _preferences.calendarEnabled);
    setUserProperty('Backups Enabled', _preferences.backupsEnabled);
    setUserProperty('Recordings Language', _preferences.recordingsLanguage);

    // setUserProperty('Memories Count', MemoryProvider().getMemoriesCount());
    // setUserProperty('Useful Memories Count', MemoryProvider().getNonDiscardedMemoriesCount());
    // setUserProperty('Messages Count', MessageProvider().getMessagesCount());
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

  void onboardingStepICompleted(String step) => track('Onboarding Step $step Completed');

  void settingsOpened() => track('Settings Opened');

  void settingsSaved() => track('Developer Settings Saved');

  void pluginsOpened() => track('Plugins Opened');

  void pluginEnabled(String pluginId) {
    track('Plugin Enabled', properties: {'plugin_id': pluginId});
    // setUserProperty('Plugins Enabled Count', _preferences.pluginsEnabled.length);
  }

  void pluginDisabled(String pluginId) {
    track('Plugin Disabled', properties: {'plugin_id': pluginId});
    // setUserProperty('Plugins Enabled Count', _preferences.pluginsEnabled.length);
  }

  void pluginRated(String pluginId, double rating) {
    track('Plugin Rated', properties: {'plugin_id': pluginId, 'rating': rating});
  }

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

  void memoryEdited(ServerMemory memory, {required String fieldEdited}) {
    var properties = getMemoryEventProperties(memory);
    properties['field_edited'] = fieldEdited;
    track('Memory Edited', properties: properties);
  }

  void chatMessageSent(String message) => track('Chat Message Sent',
      properties: {'message_length': message.length, 'message_word_count': message.split(' ').length});

  void speechProfileCapturePageClicked() => track('Speech Profile Capture Page Clicked');

  void speechProfileStarted() => track('Speech Profile Started');

  void speechProfileStartedOnboarding() => track('Speech Profile Started Onboarding');

  void speechProfileCompleted() => track('Speech Profile Completed');

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

  void backupsEnabled() {
    track('Backups Enabled');
    setUserProperty('Backups Enabled', true);
  }

  void backupsDisabled() {
    track('Backups Disabled');
    setUserProperty('Backups Enabled', false);
  }

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

  void backupsPasswordSet() => track('Backups Password Set');

  void supportContacted() => track('Support Contacted');

  void privacyDetailsPageOpened() => track('Privacy Details Page Opened');

  void joinDiscordClicked() => track('Join Discord Clicked');

  void copiedMemoryDetails(ServerMemory memory, {String source = ''}) =>
      track('Copied Memory Detail $source'.trim(), properties: getMemoryEventProperties(memory));

  void upgradeModalDismissed() => track('Upgrade Modal Dismissed');

  void upgradeModalClicked() => track('Upgrade Modal Clicked');

  void getFriendClicked() => track('Get Friend Clicked');

  void connectFriendClicked() => track('Connect Friend Clicked');

  void disconnectFriendClicked() => track('Disconnect Friend Clicked');

  void batteryIndicatorClicked() => track('Battery Indicator Clicked');

  void devModeEnabled() => track('Dev Mode Enabled');

  void devModeDisabled() => track('Dev Mode Disabled');

  void devModePageOpened() => track('Dev Mode Page Opened');

  void advancedModeDocsOpened() => track('Advanced Mode Docs Opened');

  void useWithoutDeviceOnboardingWelcome() => track('Use Without Device Onboarding Welcome');

  void useWithoutDeviceOnboardingFindDevices() => track('Use Without Device Onboarding Find Devices');

  void firmwareUpdateButtonClick() => track('Firmware Update Clicked');

  void firstTranscriptMade() => track('First Transcript Made');

// void pageViewed(String pageName) => startTimingEvent('Page View $pageName');
}
