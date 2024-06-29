import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';
import 'package:mixpanel_flutter/mixpanel_flutter.dart';

class MixpanelManager {
  static final MixpanelManager _instance = MixpanelManager._internal();
  static Mixpanel? _mixpanel;
  static final SharedPreferencesUtil _preferences = SharedPreferencesUtil();

  static Future<void> init() async {
    if (Env.mixpanelProjectToken == null) return;
    if (_mixpanel == null) {
      _mixpanel =
          await Mixpanel.init(Env.mixpanelProjectToken!, optOutTrackingDefault: false, trackAutomaticEvents: true);
      _mixpanel?.setLoggingEnabled(false);
      _instance.identify();
    }
  }

  factory MixpanelManager() {
    return _instance;
  }

  MixpanelManager._internal();

  void optInTracking() {
    _mixpanel?.optInTracking();
    identify();
  }

  void optOutTracking() {
    _mixpanel?.optOutTracking();
    _mixpanel?.reset();
  }

  void identify() => _mixpanel?.identify(_preferences.uid);

  void track(String eventName, {Map<String, dynamic>? properties}) =>
      _mixpanel?.track(eventName, properties: properties);

  void startTimingEvent(String eventName) => _mixpanel?.timeEvent(eventName);

  void onboardingDeviceConnected() => track('Onboarding Device Connected');

  void onboardingCompleted() => track('Onboarding Completed');

  void settingsOpened() => track('Settings Opened');

  void settingsSaved() => track('Developer Settings Saved');

  void pluginsOpened() => track('Plugins Opened');

  void pluginEnabled(String pluginId) => track('Plugin Enabled', properties: {'plugin_id': pluginId});

  void pluginDisabled(String pluginId) => track('Plugin Disabled', properties: {'plugin_id': pluginId});

  void recordingLanguageChanged(String language) =>
      track('Recording Language Changed', properties: {'language': language});

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

  void coachAdvisorFeedback(String t, String feedback) {
    var properties = _getTranscriptProperties(t);
    properties['transcript_language'] = _preferences.recordingsLanguage;
    properties['feedback'] = feedback;
    track('Coach Advisor Feedback', properties: properties);
  }

  Map<String, dynamic> getMemoryEventProperties(Memory memory) {
    var properties = _getTranscriptProperties(memory.transcript);
    int hoursAgo = DateTime.now().difference(memory.createdAt).inHours;
    properties['memory_hours_since_creation'] = hoursAgo;
    properties['memory_id'] = memory.id;
    return properties;
  }

  void memoryCreated(Memory memory) {
    var properties = getMemoryEventProperties(memory);
    properties['memory_result'] = memory.discarded ? 'discarded' : 'saved';
    properties['action_items_count'] = memory.structured.target!.actionItems.length;
    properties['transcript_language'] = _preferences.recordingsLanguage;
    track('Memory Created', properties: properties);
  }

  void memoryListItemClicked(Memory memory, int idx) =>
      track('Memory List Item Clicked', properties: getMemoryEventProperties(memory));

  void memoryShareButtonClick(Memory memory) =>
      track('Memory Share Button Clicked', properties: getMemoryEventProperties(memory));

  void memoryDeleted(Memory memory) => track('Memory Deleted', properties: getMemoryEventProperties(memory));

  void memoryEdited(Memory memory, {required String fieldEdited}) {
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

  void chatMessageMemoryClicked(Memory memory) =>
      track('Chat Message Memory Clicked', properties: getMemoryEventProperties(memory));

  void addManualMemoryClicked() => track('Add Manual Memory Clicked');

  void manualMemoryCreated(Memory memory) =>
      track('Manual Memory Created', properties: getMemoryEventProperties(memory));

  void setUserProperties(String whatDoYouDo, String whereDoYouPlanToUseYourFriend, String ageRange) {
    _mixpanel?.getPeople().setOnce('What the user does', whatDoYouDo);
    _mixpanel?.getPeople().setOnce('Using Friend At', whereDoYouPlanToUseYourFriend);
    _mixpanel?.getPeople().setOnce('Age Range', ageRange);
  }

  void reProcessMemory(Memory memory) => track('Re-process Memory', properties: getMemoryEventProperties(memory));

  void backupsEnabled() => track('Backups Enabled');

  void backupsDisabled() => track('Backups Disabled');

  void developerModeEnabled() => track('Developer Mode Enabled');

  void developerModeDisabled() => track('Developer Mode Disabled');

  void userIDCopied() => track('User ID Copied');

  void exportMemories() => track('Dev Mode Export Memories');

  void importMemories() => track('Dev Mode Import Memories');

  void importedMemories() => track('Dev Mode Imported Memories');

  void backupsPasswordSet() => track('Backups Password Set');

  void supportContacted() => track('Support Contacted');

  void privacyDetailsPageOpened() => track('Privacy Details Page Opened');

  void joinDiscordClicked() => track('Join Discord Clicked');

  void copiedMemoryDetails(Memory memory, {String source = ''}) =>
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

// void pageViewed(String pageName) => startTimingEvent('Page View $pageName');
}
