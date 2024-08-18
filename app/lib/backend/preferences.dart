import 'dart:convert';

import 'package:collection/collection.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/schema/bt_device.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SharedPreferencesUtil {
  static final SharedPreferencesUtil _instance = SharedPreferencesUtil._internal();
  static SharedPreferences? _preferences;

  factory SharedPreferencesUtil() {
    return _instance;
  }

  SharedPreferencesUtil._internal();

  static Future<void> init() async {
    _preferences = await SharedPreferences.getInstance();
  }

  set uid(String value) => saveString('uid', value);

  String get uid => getString('uid') ?? '';

  set btDeviceStruct(BTDeviceStruct value) {
    saveString('btDeviceStruct', jsonEncode(value.toJson()));
  }

  BTDeviceStruct get btDeviceStruct {
    final String device = getString('btDeviceStruct') ?? '';
    if (device.isEmpty) return BTDeviceStruct(id: '', name: '');
    return BTDeviceStruct.fromJson(jsonDecode(device));
  }

  set deviceName(String value) => saveString('deviceName', value);

  String get deviceName => getString('deviceName') ?? '';

  set deviceCodec(BleAudioCodec value) => saveString('deviceCodec', mapCodecToName(value));

  BleAudioCodec get deviceCodec => mapNameToCodec(getString('deviceCodec') ?? '');

  String get openAIApiKey => getString('openaiApiKey') ?? '';

  set openAIApiKey(String value) => saveString('openaiApiKey', value);

  String get gcpCredentials => getString('gcpCredentials') ?? '';

  set gcpCredentials(String value) => saveString('gcpCredentials', value);

  String get gcpBucketName => getString('gcpBucketName') ?? '';

  set gcpBucketName(String value) => saveString('gcpBucketName', value);

  String get webhookOnMemoryCreated => getString('webhookUrl') ?? '';

  set webhookOnMemoryCreated(String value) => saveString('webhookUrl', value);

  String get webhookOnTranscriptReceived => getString('transcriptServerUrl') ?? '';

  set webhookOnTranscriptReceived(String value) => saveString('transcriptServerUrl', value);

  String get recordingsLanguage => getString('recordingsLanguage') ?? 'en';

  set recordingsLanguage(String value) => saveString('recordingsLanguage', value);

  bool get useFriendApiKeys => getBool('useFriendApiKeys') ?? true;

  set useFriendApiKeys(bool value) => saveBool('useFriendApiKeys', value);

  bool get onboardingCompleted => getBool('onboardingCompleted') ?? false;

  set onboardingCompleted(bool value) => saveBool('onboardingCompleted', value);

  String get customWebsocketUrl => getString('customWebsocketUrl') ?? '';

  set customWebsocketUrl(String value) => saveString('customWebsocketUrl', value);

  String gptCompletionCache(String key) => getString('gptCompletionCache:$key') ?? '';

  setGptCompletionCache(String key, String value) => saveString('gptCompletionCache:$key', value);

  bool get optInAnalytics => getBool('optInAnalytics') ?? true;

  set optInAnalytics(bool value) => saveBool('optInAnalytics', value);

  bool get devModeEnabled => getBool('devModeEnabled') ?? false;

  set devModeEnabled(bool value) => saveBool('devModeEnabled', value);

  bool get coachNotificationIsChecked => getBool('coachIsChecked') ?? true;

  set coachNotificationIsChecked(bool value) => saveBool('coachIsChecked', value);

  bool get postMemoryNotificationIsChecked => getBool('postMemoryNotificationIsChecked') ?? true;

  set postMemoryNotificationIsChecked(bool value) => saveBool('postMemoryNotificationIsChecked', value);

  bool get reconnectNotificationIsChecked => getBool('reconnectNotificationIsChecked') ?? true;

  set reconnectNotificationIsChecked(bool value) => saveBool('reconnectNotificationIsChecked', value);

  List<String> get recordingPaths => getStringList('recordingPaths') ?? [];

  set recordingPaths(List<String> value) => saveStringList('recordingPaths', value);

  bool get hasSpeakerProfile => getBool('hasSpeakerProfile') ?? false;

  set hasSpeakerProfile(bool value) => saveBool('hasSpeakerProfile', value);

  String get locationPermissionState => getString('locationPermissionState') ?? 'UNKNOWN';

  set locationPermissionState(String value) => saveString('locationPermissionState', value);

  List<Plugin> get pluginsList {
    final List<String> plugins = getStringList('pluginsList') ?? [];
    return Plugin.fromJsonList(plugins.map((e) => jsonDecode(e)).toList());
  }

  set pluginsList(List<Plugin> value) {
    final List<String> plugins = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('pluginsList', plugins);
  }

  enablePlugin(String value) {
    final List<Plugin> plugins = pluginsList;
    final plugin = plugins.firstWhere((element) => element.id == value);
    plugin.enabled = true;
    pluginsList = plugins;
  }

  disablePlugin(String value) {
    final List<Plugin> plugins = pluginsList;
    final plugin = plugins.firstWhere((element) => element.id == value);
    plugin.enabled = false;
    pluginsList = plugins;
  }

  String get selectedChatPluginId => getString('selectedChatPluginId2') ?? 'no_selected';

  set selectedChatPluginId(String value) => saveString('selectedChatPluginId2', value);

  List<TranscriptSegment> get transcriptSegments {
    final List<String> segments = getStringList('transcriptSegments') ?? [];
    return segments.map((e) => TranscriptSegment.fromJson(jsonDecode(e))).toList();
  }

  set transcriptSegments(List<TranscriptSegment> value) {
    final List<String> segments = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('transcriptSegments', segments);
  }

  List<ServerMemory> get failedMemories {
    final List<String> memories = getStringList('failedServerMemories') ?? [];
    return memories.map((e) => ServerMemory.fromJson(jsonDecode(e))).toList();
  }

  set failedMemories(List<ServerMemory> value) {
    final List<String> memories = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('failedServerMemories', memories);
  }

  List<ServerMemory> get cachedMemories {
    final List<String> memories = getStringList('cachedMemories') ?? [];
    return memories.map((e) => ServerMemory.fromJson(jsonDecode(e))).toList();
  }

  set cachedMemories(List<ServerMemory> value) {
    final List<String> memories = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('cachedMemories', memories);
  }

  List<ServerMessage> get cachedMessages {
    final List<String> messages = getStringList('cachedMessages') ?? [];
    return messages.map((e) => ServerMessage.fromJson(jsonDecode(e))).toList();
  }

  set cachedMessages(List<ServerMessage> value) {
    final List<String> messages = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('cachedMessages', messages);
  }

  addFailedMemory(ServerMemory memory) {
    if (memory.transcriptSegments.isEmpty && memory.photos.isEmpty) return;

    final List<ServerMemory> memories = failedMemories;
    memories.add(memory);
    failedMemories = memories;
  }

  removeFailedMemory(String memoryId) {
    final List<ServerMemory> memories = failedMemories;
    ServerMemory? memory = memories.firstWhereOrNull((m) => m.id == memoryId);
    if (memory != null) {
      memories.remove(memory);
      failedMemories = memories;
    }
  }

  increaseFailedMemoryRetries(String memoryId) {
    final List<ServerMemory> memories = failedMemories;
    ServerMemory? memory = memories.firstWhereOrNull((m) => m.id == memoryId);
    if (memory != null) {
      memory.retries += 1;
      failedMemories = memories;
    }
  }

  ServerMemory? get modifiedMemoryDetails {
    final String memory = getString('modifiedMemoryDetails') ?? '';
    if (memory.isEmpty) return null;
    return ServerMemory.fromJson(jsonDecode(memory));
  }

  set modifiedMemoryDetails(ServerMemory? value) {
    saveString('modifiedMemoryDetails', value == null ? '' : jsonEncode(value.toJson()));
  }

  bool get backupsEnabled => getBool('backupsEnabled2') ?? true;

  set backupsEnabled(bool value) => saveBool('backupsEnabled2', value);

  String get lastDailySummaryDay => getString('lastDailySummaryDate') ?? '';

  set lastDailySummaryDay(String value) => saveString('lastDailySummaryDate', value);

  Future<bool> saveString(String key, String value) async {
    return await _preferences?.setString(key, value) ?? false;
  }

  String? getString(String key) {
    return _preferences?.getString(key);
  }

  Future<bool> saveInt(String key, int value) async {
    return await _preferences?.setInt(key, value) ?? false;
  }

  int? getInt(String key) {
    return _preferences?.getInt(key);
  }

  Future<bool> saveBool(String key, bool value) async {
    return await _preferences?.setBool(key, value) ?? false;
  }

  bool? getBool(String key) {
    return _preferences?.getBool(key);
  }

  Future<bool> saveDouble(String key, double value) async {
    return await _preferences?.setDouble(key, value) ?? false;
  }

  double? getDouble(String key) {
    return _preferences?.getDouble(key);
  }

  Future<bool> saveStringList(String key, List<String> value) async {
    return await _preferences?.setStringList(key, value) ?? false;
  }

  List<String>? getStringList(String key) {
    return _preferences?.getStringList(key);
  }

  Future<bool> remove(String key) async {
    return await _preferences?.remove(key) ?? false;
  }

  Future<bool> clear() async {
    return await _preferences?.clear() ?? false;
  }

  set scriptCategoriesAndEmojisExecuted(bool value) => saveBool('scriptCategoriesAndEmojisExecuted', value);

  bool get scriptCategoriesAndEmojisExecuted => getBool('scriptCategoriesAndEmojisExecuted') ?? false;

  set scriptMemoryVectorsExecuted(bool value) => saveBool('scriptMemoryVectorsExecuted2', value);

  bool get scriptMemoryVectorsExecuted => getBool('scriptMemoryVectorsExecuted2') ?? false;

  set scriptMigrateMemoriesToBack(bool value) => saveBool('scriptMigrateMemoriesToBack2', value);

  bool get scriptMigrateMemoriesToBack => getBool('scriptMigrateMemoriesToBack2') ?? false;

  set scriptMemoriesToObjectBoxExecuted(bool value) => saveBool('scriptMemoriesToObjectBoxExecuted', value);

  bool get scriptMemoriesToObjectBoxExecuted => getBool('scriptMemoriesToObjectBoxExecuted') ?? false;

  set pageToShowFromNotification(int value) => saveInt('pageToShowFromNotification', value);

  int get pageToShowFromNotification => getInt('pageToShowFromNotification') ?? 1;

  set subPageToShowFromNotification(String value) => saveString('subPageToShowFromNotification', value);

  String get subPageToShowFromNotification => getString('subPageToShowFromNotification') ?? '';

  set calendarPermissionAlreadyRequested(bool value) => saveBool('calendarPermissionAlreadyRequested', value);

  bool get calendarPermissionAlreadyRequested => getBool('calendarPermissionAlreadyRequested') ?? false;

  set calendarEnabled(bool value) => saveBool('calendarEnabled', value);

  bool get calendarEnabled => getBool('calendarEnabled') ?? false;

  set calendarId(String value) => saveString('calendarId', value);

  String get calendarId => getString('calendarId') ?? '';

  set calendarType(String value) => saveString('calendarType', value); // auto, manual

  String get calendarType => getString('calendarType') ?? 'auto';

  bool get firstTranscriptMade => getBool('firstTranscriptMade') ?? false;

  set firstTranscriptMade(bool value) => saveBool('firstTranscriptMade', value);

  // AUTH

  String get authToken => getString('authToken') ?? '';

  set authToken(String value) => saveString('authToken', value);

  int get tokenExpirationTime => getInt('tokenExpirationTime') ?? 0;

  set tokenExpirationTime(int value) => saveInt('tokenExpirationTime', value);

  String get email => getString('email') ?? '';

  set email(String value) => saveString('email', value);

  String get givenName => getString('givenName') ?? '';

  set givenName(String value) => saveString('givenName', value);

  String get familyName => getString('familyName') ?? '';

  set familyName(String value) => saveString('familyName', value);

  String get fullName => '$givenName $familyName';

  set locationPermissionRequested(bool value) => saveBool('locationPermissionRequested', value);

  bool get locationPermissionRequested => getBool('locationPermissionRequested') ?? false;
}
