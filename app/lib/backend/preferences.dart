import 'dart:convert';

import 'package:collection/collection.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/backend/schema/person.dart';
import 'package:friend_private/services/wals.dart';
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

  //-------------------------------- Device ----------------------------------//

  set btDevice(BtDevice value) {
    saveString('btDevice', jsonEncode(value.toJson()));
  }

  Future<void> btDeviceSet(BtDevice value) async {
    await saveString('btDevice', jsonEncode(value.toJson()));
  }

  BtDevice get btDevice {
    final String device = getString('btDevice') ?? '';
    if (device.isEmpty) return BtDevice(id: '', name: '', type: DeviceType.friend, rssi: 0);
    return BtDevice.fromJson(jsonDecode(device));
  }

  set deviceName(String value) => saveString('deviceName', value);

  String get deviceName => getString('deviceName') ?? '';

  set deviceCodec(BleAudioCodec value) => saveString('deviceCodec', mapCodecToName(value));

  Future setDeviceCodec(BleAudioCodec value) => saveString('deviceCodec', mapCodecToName(value));

  BleAudioCodec get deviceCodec => mapNameToCodec(getString('deviceCodec') ?? '');

  bool get deviceIsV2 => getBool('deviceIsV2') ?? false;

  set deviceIsV2(bool value) => saveBool('deviceIsV2', value);

  String get openAIApiKey => getString('openaiApiKey') ?? '';

  set openAIApiKey(String value) => saveString('openaiApiKey', value);

  //----------------------------- Permissions ---------------------------------//

  set notificationsEnabled(bool value) => saveBool('notificationsEnabled', value);

  bool get notificationsEnabled => getBool('notificationsEnabled') ?? false;

  set locationEnabled(bool value) => saveBool('locationEnabled', value);

  bool get locationEnabled => getBool('locationEnabled') ?? false;

  //---------------------- Developer Settings ---------------------------------//

  String get gcpCredentials => getString('gcpCredentials') ?? '';

  set gcpCredentials(String value) => saveString('gcpCredentials', value);

  String get gcpBucketName => getString('gcpBucketName') ?? '';

  set gcpBucketName(String value) => saveString('gcpBucketName', value);

  String get webhookOnMemoryCreated => getString('webhookOnMemoryCreated') ?? '';

  set webhookOnMemoryCreated(String value) => saveString('webhookOnMemoryCreated', value);

  String get webhookOnTranscriptReceived => getString('webhookOnTranscriptReceived') ?? '';

  set webhookOnTranscriptReceived(String value) => saveString('webhookOnTranscriptReceived', value);

  String get webhookAudioBytes => getString('webhookAudioBytes') ?? '';

  set webhookAudioBytes(String value) => saveString('webhookAudioBytes', value);

  String get webhookAudioBytesDelay => getString('webhookAudioBytesDelay') ?? '';

  set webhookDaySummary(String value) => saveString('webhookDaySummary', value);

  String get webhookDaySummary => getString('webhookDaySummary') ?? '';

  set webhookAudioBytesDelay(String value) => saveString('webhookAudioBytesDelay', value);

  set devModeJoanFollowUpEnabled(bool value) => saveBool('devModeJoanFollowUpEnabled', value);

  bool get devModeJoanFollowUpEnabled => getBool('devModeJoanFollowUpEnabled') ?? false;

  set memoryEventsToggled(bool value) => saveBool('memoryEventsToggled', value);

  bool get memoryEventsToggled => getBool('memoryEventsToggled') ?? false;

  set transcriptsToggled(bool value) => saveBool('transcriptsToggled', value);

  bool get transcriptsToggled => getBool('transcriptsToggled') ?? false;

  set audioBytesToggled(bool value) => saveBool('audioBytesToggled', value);

  bool get audioBytesToggled => getBool('audioBytesToggled') ?? false;

  set daySummaryToggled(bool value) => saveBool('daySummaryToggled', value);

  bool get daySummaryToggled => getBool('daySummaryToggled') ?? false;

  set localSyncEnabled(bool value) => saveBool('localSyncEnabled', value);

  bool get localSyncEnabled => getBool('localSyncEnabled') ?? true;

  bool get showSummarizeConfirmation => getBool('showSummarizeConfirmation') ?? true;

  set showSummarizeConfirmation(bool value) => saveBool('showSummarizeConfirmation', value);

  bool get showSubmitAppConfirmation => getBool('showSubmitAppConfirmation') ?? true;

  set showSubmitAppConfirmation(bool value) => saveBool('showSubmitAppConfirmation', value);

  String get recordingsLanguage => getString('recordingsLanguage') ?? 'en';

  set recordingsLanguage(String value) => saveString('recordingsLanguage', value);

  String get transcriptionModel => getString('transcriptionModel3') ?? 'soniox';

  set transcriptionModel(String value) => saveString('transcriptionModel3', value);

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

  bool get optInEmotionalFeedback => getBool('optInEmotionalFeedback') ?? false;

  set optInEmotionalFeedback(bool value) => saveBool('optInEmotionalFeedback', value);

  bool get devModeEnabled => getBool('devModeEnabled') ?? false;

  set devModeEnabled(bool value) => saveBool('devModeEnabled', value);

  bool get permissionStoreRecordingsEnabled => getBool('permissionStoreRecordingsEnabled') ?? false;

  set permissionStoreRecordingsEnabled(bool value) => saveBool('permissionStoreRecordingsEnabled', value);

  bool get hasSpeakerProfile => getBool('hasSpeakerProfile') ?? false;

  set hasSpeakerProfile(bool value) => saveBool('hasSpeakerProfile', value);

  bool get showDiscardedMemories => getBool('showDiscardedMemories') ?? true;

  set showDiscardedMemories(bool value) => saveBool('showDiscardedMemories', value);

  int get currentStorageBytes => getInt('currentStorageBytes') ?? 0;

  set currentStorageBytes(int value) => saveInt('currentStorageBytes', value);

  int get previousStorageBytes => getInt('previousStorageBytes') ?? 0;

  set previousStorageBytes(int value) => saveInt('previousStorageBytes', value);

  int get enabledAppsCount => appsList.where((element) => element.enabled).length;

  int get enabledAppsIntegrationsCount =>
      appsList.where((element) => element.enabled && element.worksExternally()).length;

  List<App> get appsList {
    final List<String> apps = getStringList('appsList') ?? [];
    return App.fromJsonList(apps.map((e) => jsonDecode(e)).toList());
  }

  set appsList(List<App> value) {
    final List<String> apps = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('appsList', apps);
  }

  enableApp(String value) {
    final List<App> apps = appsList;
    final app = apps.firstWhere((element) => element.id == value);
    app.enabled = true;
    appsList = apps;
  }

  disableApp(String value) {
    final List<App> apps = appsList;
    final app = apps.firstWhere((element) => element.id == value);
    app.enabled = false;
    appsList = apps;
  }

  String get selectedChatAppId => getString('selectedChatAppId2') ?? 'no_selected';

  set selectedChatAppId(String value) => saveString('selectedChatAppId2', value);

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

  List<Person> get cachedPeople {
    final List<String> people = getStringList('cachedPeople') ?? [];
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

  set scriptCategoriesAndEmojisExecuted(bool value) => saveBool('scriptCategoriesAndEmojisExecuted', value);

  bool get scriptCategoriesAndEmojisExecuted => getBool('scriptCategoriesAndEmojisExecuted') ?? false;

  set scriptMemoryVectorsExecuted(bool value) => saveBool('scriptMemoryVectorsExecuted2', value);

  bool get scriptMemoryVectorsExecuted => getBool('scriptMemoryVectorsExecuted2') ?? false;

  set scriptMigrateMemoriesToBack(bool value) => saveBool('scriptMigrateMemoriesToBack2', value);

  bool get scriptMigrateMemoriesToBack => getBool('scriptMigrateMemoriesToBack2') ?? false;

  set pageToShowFromNotification(int value) => saveInt('pageToShowFromNotification', value);

  int get pageToShowFromNotification => getInt('pageToShowFromNotification') ?? 0;

  set subPageToShowFromNotification(String value) => saveString('subPageToShowFromNotification', value);

  String get subPageToShowFromNotification => getString('subPageToShowFromNotification') ?? '';

  set calendarPermissionAlreadyRequested(bool value) => saveBool('calendarPermissionAlreadyRequested', value);

  bool get calendarPermissionAlreadyRequested => getBool('calendarPermissionAlreadyRequested') ?? false;

  set calendarEnabled(bool value) => saveBool('calendarEnabled', value);

  bool get calendarEnabled => getBool('calendarEnabled') ?? false;

  set calendarId(String value) => saveString('calendarId', value);

  String get calendarId => getString('calendarId') ?? '';

  set calendarType(String value) => saveString('calendarType2', value); // auto, manual (only for now)

  String get calendarType => getString('calendarType2') ?? 'manual';

  bool get firstTranscriptMade => getBool('firstTranscriptMade') ?? false;

  set firstTranscriptMade(bool value) => saveBool('firstTranscriptMade', value);

  //--------------------------------- Auth ------------------------------------//

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

  String get fullName => '$givenName $familyName'.trim();

  set locationPermissionRequested(bool value) => saveBool('locationPermissionRequested', value);

  bool get locationPermissionRequested => getBool('locationPermissionRequested') ?? false;

  //--------------------------------- Wals ------------------------------------//

  set wals(List<Wal> wals) {
    final List<String> value = wals.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('wals', value);
  }

  List<Wal> get wals {
    final List<String> value = getStringList('wals') ?? [];
    return Wal.fromJsonList(value.map((e) => jsonDecode(e)).toList());
  }

  //--------------------------- Setters & Getters -----------------------------//

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

  String get customBackendUrl => getString('customBackendUrl') ?? '';

  set customBackendUrl(String value) => saveString('customBackendUrl', value);

  String get customAuthPassword => getString('customAuthPassword') ?? '';

  set customAuthPassword(String value) => saveString('customAuthPassword', value);
}
