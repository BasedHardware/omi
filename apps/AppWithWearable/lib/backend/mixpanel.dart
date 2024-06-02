import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
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

  void onboardingCompleted() => track('Onboarding Completed');

  void settingsOpened() => track('Settings Opened');

  void settingsSaved() => track('Settings Saved');

  void pluginsOpened() => track('Settings Saved');

  void devModeEnabled() => track('Dev Mode Enabled');

  void devModeDisabled() => track('Dev Mode Disabled');

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

  Map<String, dynamic> _getMemoryEventProperties(MemoryRecord memory) {
    var properties = _getTranscriptProperties(memory.transcript);
    int hoursAgo = DateTime.now().difference(memory.createdAt).inHours;
    properties['memory_hours_since_creation'] = hoursAgo;
    properties['memory_id'] = memory.id;
    return properties;
  }

  void memoryCreated(MemoryRecord memory) {
    var properties = _getMemoryEventProperties(memory);
    properties['memory_result'] = memory.discarded ? 'discarded' : 'saved';
    properties['action_items_count'] = memory.structured.actionItems.length;
    properties['transcript_language'] = _preferences.recordingsLanguage;
    track('Memory Created', properties: properties);
  }

  void memoryListItemClicked(MemoryRecord memory, int idx) =>
      track('Memory List Item Clicked', properties: _getMemoryEventProperties(memory));

  void memoryShareButtonClick(MemoryRecord memory) =>
      track('Memory Share Button Clicked', properties: _getMemoryEventProperties(memory));

  void memoryDeleted(MemoryRecord memory) => track('Memory Deleted', properties: _getMemoryEventProperties(memory));

  void memoryEdited(MemoryRecord memory, {required String fieldEdited}) {
    var properties = _getMemoryEventProperties(memory);
    properties['field_edited'] = fieldEdited;
    track('Memory Edited', properties: properties);
  }

  void chatMessageSent(String message) {
    track('Chat Message Sent',
        properties: {'message_length': message.length, 'message_word_count': message.split(' ').length});
  }

// TBI
// void pageViewed(String pageName) => startTimingEvent('Page View $pageName');
}
