import 'dart:convert';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SharedPreferencesUtil {
  static final SharedPreferencesUtil _instance = SharedPreferencesUtil._internal();
  static SharedPreferences? _preferences;

  factory SharedPreferencesUtil() {
    return _instance;
  }

  SharedPreferencesUtil._internal();

  String get deviceIdHash => _preferences?.getString('deviceIdHash') ?? '';
  set deviceIdHash(String value) => _preferences?.setString('deviceIdHash', value);

  static Future<void> init() async {
    _preferences = await SharedPreferences.getInstance();
  }

  set uid(String value) => saveString('uid', value);

  String get uid => getString('uid');

  //-------------------------------- Device ----------------------------------//

  bool? get hasOmiDevice => _preferences?.getBool('hasOmiDevice');

  set hasOmiDevice(bool? value) {
    if (value != null) {
      _preferences?.setBool('hasOmiDevice', value);
    } else {
      _preferences?.remove('hasOmiDevice');
    }
  }

  bool get hasPersonaCreated => getBool('hasPersonaCreated') ?? false;

  set hasPersonaCreated(bool value) => saveBool('hasPersonaCreated', value);

  String? get verifiedPersonaId => getString('verifiedPersonaId');

  set verifiedPersonaId(String? value) {
    if (value != null) {
      _preferences?.setString('verifiedPersonaId', value);
    } else {
      _preferences?.remove('verifiedPersonaId');
    }
  }

  set btDevice(BtDevice value) {
    saveString('btDevice', jsonEncode(value.toJson()));
  }

  Future<void> btDeviceSet(BtDevice value) async {
    await saveString('btDevice', jsonEncode(value.toJson()));
  }

  BtDevice get btDevice {
    final String device = getString('btDevice') ?? '';
    if (device.isEmpty) return BtDevice(id: '', name: '', type: DeviceType.omi, rssi: 0);
    return BtDevice.fromJson(jsonDecode(device));
  }

  set deviceName(String value) => saveString('deviceName', value);

  String get deviceName => getString('deviceName');

  bool get deviceIsV2 => getBool('deviceIsV2');

  set deviceIsV2(bool value) => saveBool('deviceIsV2', value);

  // Double tap behavior: 0 = end conversation (default), 1 = pause/mute, 2 = star ongoing conversation
  int get doubleTapAction => getInt('doubleTapAction');

  set doubleTapAction(int value) => saveInt('doubleTapAction', value);

  // Keep backward compatibility
  bool get doubleTapPausesMuting => doubleTapAction == 1;

  set doubleTapPausesMuting(bool value) => doubleTapAction = value ? 1 : 0;

  // Custom STT configuration
  CustomSttConfig get customSttConfig {
    final configJson = getString('customSttConfig');
    if (configJson.isEmpty) return CustomSttConfig.defaultConfig;
    try {
      return CustomSttConfig.fromJson(jsonDecode(configJson));
    } catch (e, stack) {
      debugPrint('Error parsing customSttConfig: $e');
      debugPrint('Stack: $stack');
      return CustomSttConfig.defaultConfig;
    }
  }

  Future<bool> saveCustomSttConfig(CustomSttConfig value) async {
    return await saveString('customSttConfig', jsonEncode(value.toJson()));
  }

  bool get useCustomStt => customSttConfig.isEnabled;

  // Per-provider config storage
  CustomSttConfig? getConfigForProvider(SttProvider provider) {
    final json = getString('sttConfig_${provider.name}');
    if (json.isEmpty) return null;
    try {
      return CustomSttConfig.fromJson(jsonDecode(json));
    } catch (e) {
      debugPrint('Error loading config for ${provider.name}: $e');
      return null;
    }
  }

  Future<bool> saveConfigForProvider(SttProvider provider, CustomSttConfig config) {
    return saveString('sttConfig_${provider.name}', jsonEncode(config.toJson()));
  }

  //----------------------------- Permissions ---------------------------------//

  set notificationsEnabled(bool value) => saveBool('notificationsEnabled', value);

  bool get notificationsEnabled => getBool('notificationsEnabled');

  set locationEnabled(bool value) => saveBool('locationEnabled', value);

  bool get locationEnabled => getBool('locationEnabled');

  //---------------------- Developer Settings ---------------------------------//

  String get webhookOnConversationCreated => getString('webhookOnConversationCreated');

  set webhookOnConversationCreated(String value) => saveString('webhookOnConversationCreated', value);

  String get webhookOnTranscriptReceived => getString('webhookOnTranscriptReceived');

  set webhookOnTranscriptReceived(String value) => saveString('webhookOnTranscriptReceived', value);

  String get webhookAudioBytes => getString('webhookAudioBytes');

  set webhookAudioBytes(String value) => saveString('webhookAudioBytes', value);

  String get webhookAudioBytesDelay => getString('webhookAudioBytesDelay');

  set webhookDaySummary(String value) => saveString('webhookDaySummary', value);

  String get webhookDaySummary => getString('webhookDaySummary');

  set webhookAudioBytesDelay(String value) => saveString('webhookAudioBytesDelay', value);

  set devModeJoanFollowUpEnabled(bool value) => saveBool('devModeJoanFollowUpEnabled', value);

  bool get devModeJoanFollowUpEnabled => getBool('devModeJoanFollowUpEnabled');

  set transcriptionDiagnosticEnabled(bool value) => saveBool('transcriptionDiagnosticEnabled', value);

  bool get transcriptionDiagnosticEnabled => getBool('transcriptionDiagnosticEnabled');

  set autoCreateSpeakersEnabled(bool value) => saveBool('autoCreateSpeakersEnabled', value);

  bool get autoCreateSpeakersEnabled => getBool('autoCreateSpeakersEnabled', defaultValue: true);

  // Goal tracker widget on homepage - default is true (experimental feature)
  set showGoalTrackerEnabled(bool value) => saveBool('showGoalTrackerEnabled', value);

  bool get showGoalTrackerEnabled => getBool('showGoalTrackerEnabled', defaultValue: true);

  // Daily reflection notification at 9 PM - default is true (enabled)
  set dailyReflectionEnabled(bool value) => saveBool('dailyReflectionEnabled', value);

  bool get dailyReflectionEnabled => getBool('dailyReflectionEnabled', defaultValue: true);

  // Wrapped 2025 - track if user has viewed their wrapped
  set hasViewedWrapped2025(bool value) => saveBool('hasViewedWrapped2025', value);

  bool get hasViewedWrapped2025 => getBool('hasViewedWrapped2025', defaultValue: false);

  set conversationEventsToggled(bool value) => saveBool('conversationEventsToggled', value);

  bool get conversationEventsToggled => getBool('conversationEventsToggled');

  set transcriptsToggled(bool value) => saveBool('transcriptsToggled', value);

  bool get transcriptsToggled => getBool('transcriptsToggled');

  set audioBytesToggled(bool value) => saveBool('audioBytesToggled', value);

  bool get audioBytesToggled => getBool('audioBytesToggled');

  set daySummaryToggled(bool value) => saveBool('daySummaryToggled', value);

  bool get daySummaryToggled => getBool('daySummaryToggled');

  bool get showSummarizeConfirmation => getBool('showSummarizeConfirmation', defaultValue: true);

  set showSummarizeConfirmation(bool value) => saveBool('showSummarizeConfirmation', value);

  bool get showSubmitAppConfirmation => getBool('showSubmitAppConfirmation', defaultValue: true);

  set showSubmitAppConfirmation(bool value) => saveBool('showSubmitAppConfirmation', value);

  bool get showInstallAppConfirmation => getBool('showInstallAppConfirmation', defaultValue: true);

  set showInstallAppConfirmation(bool value) => saveBool('showInstallAppConfirmation', value);

  bool get showFirmwareUpdateDialog => getBool('v2/showFirmwareUpdateDialog', defaultValue: true);

  set showFirmwareUpdateDialog(bool value) => saveBool('v2/showFirmwareUpdateDialog', value);

  int get conversationSilenceDuration => getInt('conversationSilenceDuration', defaultValue: 120);

  set conversationSilenceDuration(int value) => saveInt('conversationSilenceDuration', value);

  String get transcriptionModel => getString('transcriptionModel3', defaultValue: 'soniox');

  set transcriptionModel(String value) => saveString('transcriptionModel3', value);

  bool get onboardingCompleted => getBool('onboardingCompleted');

  set onboardingCompleted(bool value) => saveBool('onboardingCompleted', value);

  String gptCompletionCache(String key) => getString('gptCompletionCache:$key');

  setGptCompletionCache(String key, String value) => saveString('gptCompletionCache:$key', value);

  bool get optInAnalytics => getBool('optInAnalytics') ?? (PlatformService.isDesktop ? false : true);

  set optInAnalytics(bool value) => saveBool('optInAnalytics', value);

  bool get optInEmotionalFeedback => getBool('optInEmotionalFeedback');

  set optInEmotionalFeedback(bool value) => saveBool('optInEmotionalFeedback', value);

  bool get devModeEnabled => getBool('devModeEnabled');

  set devModeEnabled(bool value) => saveBool('devModeEnabled', value);

  // Auto-recording feature (macOS only)
  bool get autoRecordingEnabled => getBool('autoRecordingEnabled', defaultValue: true);

  set autoRecordingEnabled(bool value) => saveBool('autoRecordingEnabled', value);

  // Developer Diagnostics
  bool get devLogsToFileEnabled => getBool('devLogsToFileEnabled');

  set devLogsToFileEnabled(bool value) => saveBool('devLogsToFileEnabled', value);

  bool get permissionStoreRecordingsEnabled => getBool('permissionStoreRecordingsEnabled');

  set permissionStoreRecordingsEnabled(bool value) => saveBool('permissionStoreRecordingsEnabled', value);

  bool get unlimitedLocalStorageEnabled => getBool('unlimitedLocalStorageEnabled');

  set unlimitedLocalStorageEnabled(bool value) => saveBool('unlimitedLocalStorageEnabled', value);

  bool get hasSpeakerProfile => getBool('hasSpeakerProfile');

  set hasSpeakerProfile(bool value) => saveBool('hasSpeakerProfile', value);

  bool get showDiscardedMemories => getBool('showDiscardedMemories', defaultValue: false);

  set showDiscardedMemories(bool value) => saveBool('showDiscardedMemories', value);

  // Show short conversations - default is false (hidden)
  bool get showShortConversations => getBool('showShortConversations', defaultValue: false);

  set showShortConversations(bool value) => saveBool('showShortConversations', value);

  // Short conversation threshold in seconds - default is 60 (1 minute)
  // Options: 60 (1 min), 120 (2 min), 180 (3 min), 240 (4 min), 300 (5 min)
  int get shortConversationThreshold => getInt('v2/shortConversationThreshold', defaultValue: 0);

  set shortConversationThreshold(int value) => saveInt('v2/shortConversationThreshold', value);

  // Transcription settings (cached for fast preload)
  bool get cachedSingleLanguageMode => getBool('cachedSingleLanguageMode');

  set cachedSingleLanguageMode(bool value) => saveBool('cachedSingleLanguageMode', value);

  List<String> get cachedTranscriptionVocabulary => getStringList('cachedTranscriptionVocabulary');

  set cachedTranscriptionVocabulary(List<String> value) => saveStringList('cachedTranscriptionVocabulary', value);

  // User primary language preferences
  String get userPrimaryLanguage => getString('userPrimaryLanguage');

  set userPrimaryLanguage(String value) => saveString('userPrimaryLanguage', value);

  bool get hasSetPrimaryLanguage => getBool('hasSetPrimaryLanguage');

  set hasSetPrimaryLanguage(bool value) => saveBool('hasSetPrimaryLanguage', value);

  int get currentStorageBytes => getInt('currentStorageBytes');

  set currentStorageBytes(int value) => saveInt('currentStorageBytes', value);

  int get previousStorageBytes => getInt('previousStorageBytes');

  set previousStorageBytes(int value) => saveInt('previousStorageBytes', value);

  int get enabledAppsCount => appsList.where((element) => element.enabled).length;

  int get enabledAppsIntegrationsCount =>
      appsList.where((element) => element.enabled && element.worksExternally()).length;

  bool get showConversationDeleteConfirmation => getBool('showConversationDeleteConfirmation', defaultValue: true);

  set showConversationDeleteConfirmation(bool value) => saveBool("showConversationDeleteConfirmation", value);

  bool get showActionItemDeleteConfirmation => getBool('showActionItemDeleteConfirmation', defaultValue: true);

  set showActionItemDeleteConfirmation(bool value) => saveBool('showActionItemDeleteConfirmation', value);

  bool get showGetOmiCard => getBool('showGetOmiCard', defaultValue: true);

  set showGetOmiCard(bool value) => saveBool('showGetOmiCard', value);

  List<App> get appsList {
    final apps = getStringList('appsList');
    return App.fromJsonList(apps.map((e) => jsonDecode(e)).toList());
  }

  set appsList(List<App> value) {
    final List<String> apps = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('appsList', apps);
  }

  enableApp(String value) {
    final List<App> apps = appsList;
    App? app = apps.firstWhereOrNull((element) => element.id == value);
    if (app != null) {
      app.enabled = true;
      appsList = apps;
    }
  }

  disableApp(String value) {
    final List<App> apps = appsList;
    App? app = apps.firstWhereOrNull((element) => element.id == value);
    if (app != null) {
      app.enabled = false;
      appsList = apps;
    }
  }

  String get selectedChatAppId => getString('selectedChatAppId2', defaultValue: 'no_selected');

  set selectedChatAppId(String value) => saveString('selectedChatAppId2', value);

  String get lastUsedSummarizationAppId => getString('lastUsedSummarizationAppId');

  set lastUsedSummarizationAppId(String value) => saveString('lastUsedSummarizationAppId', value);

  String get preferredSummarizationAppId => getString('preferredSummarizationAppId');

  set preferredSummarizationAppId(String value) => saveString('preferredSummarizationAppId', value);

  List<ServerConversation> get cachedConversations {
    if (getBool('migratedMemories')) {
      final cachedMemories = getStringList('cachedMemories');
      if (cachedMemories.isNotEmpty) {
        final conversations = cachedMemories.map((e) => ServerConversation.fromJson(jsonDecode(e))).toList();
        cachedConversations = conversations;
        saveBool('migratedMemories', true);
      }
    }
    final conversations = getStringList('cachedConversations');
    return conversations.map((e) => ServerConversation.fromJson(jsonDecode(e))).toList();
  }

  set cachedConversations(List<ServerConversation> value) {
    final List<String> conversations = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('cachedConversations', conversations);
  }

  List<ServerMessage> get cachedMessages {
    final messages = getStringList('cachedMessages');
    return messages.map((e) => ServerMessage.fromJson(jsonDecode(e))).toList();
  }

  set cachedMessages(List<ServerMessage> value) {
    final List<String> messages = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('cachedMessages', messages);
  }

  // Pending memories - memories created offline that need to be synced
  List<Memory> get pendingMemories {
    final memories = getStringList('pendingMemories');
    return memories.map((e) => Memory.fromJson(jsonDecode(e))).toList();
  }

  set pendingMemories(List<Memory> value) {
    final List<String> memories = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('pendingMemories', memories);
  }

  void addPendingMemory(Memory memory) {
    final List<Memory> memories = pendingMemories;
    memories.add(memory);
    pendingMemories = memories;
  }

  void removePendingMemory(String memoryId) {
    final List<Memory> memories = pendingMemories;
    memories.removeWhere((m) => m.id == memoryId);
    pendingMemories = memories;
  }

  void clearPendingMemories() {
    saveStringList('pendingMemories', []);
  }

  List<Person> get cachedPeople {
    final people = getStringList('cachedPeople');
    return people.map((e) => Person.fromJson(jsonDecode(e))).toList();
  }

  Person? getPersonById(String id) {
    return cachedPeople.firstWhereOrNull((element) => element.id == id);
  }

  set cachedPeople(List<Person> value) {
    final List<String> people = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('cachedPeople', people);
  }

  addCachedPerson(Person person) {
    final List<Person> people = cachedPeople;
    people.add(person);
    cachedPeople = people;
  }

  removeCachedPerson(String personId) {
    final List<Person> people = cachedPeople;
    Person? person = people.firstWhereOrNull((p) => p.id == personId);
    if (person != null) {
      people.remove(person);
      cachedPeople = people;
    }
  }

  replaceCachedPerson(Person person) {
    final List<Person> people = cachedPeople;
    Person? oldPerson = people.firstWhereOrNull((p) => p.id == person.id);
    if (oldPerson != null) {
      people.remove(oldPerson);
      people.add(person);
      cachedPeople = people;
    }
  }

  ServerConversation? get modifiedConversationDetails {
    final String conversation = getString('modifiedConversationDetails') ?? '';
    if (conversation.isEmpty) return null;
    return ServerConversation.fromJson(jsonDecode(conversation));
  }

  set modifiedConversationDetails(ServerConversation? value) {
    saveString('modifiedConversationDetails', value == null ? '' : jsonEncode(value.toJson()));
  }

  set calendarPermissionAlreadyRequested(bool value) => saveBool('calendarPermissionAlreadyRequested', value);

  bool get calendarPermissionAlreadyRequested => getBool('calendarPermissionAlreadyRequested');

  set calendarEnabled(bool value) => saveBool('calendarEnabled', value);

  bool get calendarEnabled => getBool('calendarEnabled');

  set calendarId(String value) => saveString('calendarId', value);

  String get calendarId => getString('calendarId');

  set calendarType(String value) => saveString('calendarType2', value); // auto, manual (only for now)

  String get calendarType => getString('calendarType2', defaultValue: 'manual');

  set calendarIntegrationEnabled(bool value) => saveBool('calendarIntegrationEnabled', value);

  bool get calendarIntegrationEnabled => getBool('calendarIntegrationEnabled') ?? false;

  // Calendar UI Settings
  set showEventsWithNoParticipants(bool value) => saveBool('showEventsWithNoParticipants', value);

  bool get showEventsWithNoParticipants => getBool('showEventsWithNoParticipants') ?? false;

  set showMeetingsInMenuBar(bool value) => saveBool('showMeetingsInMenuBar', value);

  bool get showMeetingsInMenuBar => getBool('showMeetingsInMenuBar') ?? true;

  set enabledCalendarIds(List<String> value) => saveStringList('enabledCalendarIds', value);

  List<String> get enabledCalendarIds => getStringList('enabledCalendarIds') ?? [];

  //--------------------------------- Auth ------------------------------------//

  String get authToken => getString('authToken');

  set authToken(String value) => saveString('authToken', value);

  int get tokenExpirationTime => getInt('tokenExpirationTime');

  set tokenExpirationTime(int value) => saveInt('tokenExpirationTime', value);

  String get email => getString('email');

  set email(String value) => saveString('email', value);

  String get givenName => getString('givenName');

  set givenName(String value) => saveString('givenName', value);

  String get familyName => getString('familyName');

  set familyName(String value) => saveString('familyName', value);

  String get fullName => '$givenName $familyName'.trim();

  set locationPermissionRequested(bool value) => saveBool('locationPermissionRequested', value);

  bool get locationPermissionRequested => getBool('locationPermissionRequested');

  //--------------------------- Setters & Getters -----------------------------//

  String getString(String key, {String defaultValue = ''}) => _preferences?.getString(key) ?? defaultValue;

  int getInt(String key, {int defaultValue = 0}) => _preferences?.getInt(key) ?? defaultValue;

  bool getBool(String key, {bool defaultValue = false}) => _preferences?.getBool(key) ?? defaultValue;

  double getDouble(String key, {double defaultValue = 0.0}) => _preferences?.getDouble(key) ?? defaultValue;

  List<String> getStringList(String key, {List<String> defaultValue = const []}) =>
      _preferences?.getStringList(key) ?? defaultValue;

  Future<bool> saveString(String key, String value) async => await _preferences?.setString(key, value) ?? false;

  Future<bool> saveInt(String key, int value) async => await _preferences?.setInt(key, value) ?? false;

  Future<bool> saveBool(String key, bool value) async => await _preferences?.setBool(key, value) ?? false;

  Future<bool> saveDouble(String key, double value) async => await _preferences?.setDouble(key, value) ?? false;

  Future<bool> saveStringList(String key, List<String> value) async =>
      await _preferences?.setStringList(key, value) ?? false;

  Future<bool> remove(String key) async => await _preferences?.remove(key) ?? false;

  Future<bool> clear() async => await _preferences?.clear() ?? false;
}
