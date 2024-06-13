import 'dart:convert';

import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/backend/storage/plugin.dart';
import 'package:friend_private/backend/storage/segment.dart';
import 'package:friend_private/env/env.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

class SharedPreferencesUtil {
  static final SharedPreferencesUtil _instance = SharedPreferencesUtil._internal();
  static SharedPreferences? _preferences;

  factory SharedPreferencesUtil() {
    return _instance;
  }

  SharedPreferencesUtil._internal();

  static Future<void> init() async {
    _preferences = await SharedPreferences.getInstance();
    // _preferences!.clear();
    if (!_preferences!.containsKey('uid')) {
      _preferences!.setString('uid', const Uuid().v4());
    }
  }

  String get uid => getString('uid') ?? '';

  set deviceId(String value) => saveString('deviceId', value);

  String get deviceId => getString('deviceId') ?? '';

  String get openAIApiKey => getString('openaiApiKey') ?? '';

  set openAIApiKey(String value) => saveString('openaiApiKey', value);

  String get gcpCredentials => getString('gcpCredentials') ?? '';

  set gcpCredentials(String value) => saveString('gcpCredentials', value);

  String get gcpBucketName => getString('gcpBucketName') ?? '';

  set gcpBucketName(String value) => saveString('gcpBucketName', value);

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

  bool get coachIsChecked => getBool('coachIsChecked') ?? true;

  set coachIsChecked(bool value) => saveBool('coachIsChecked', value);

  bool get reconnectNotificationIsChecked => getBool('reconnectNotificationIsChecked') ?? true;

  set reconnectNotificationIsChecked(bool value) => saveBool('reconnectNotificationIsChecked', value);

  List<Message> get chatMessages {
    final List<String> messages = getStringList('messages') ?? [];
    return messages.map((e) => Message.fromJson(jsonDecode(e))).toList();
  }

  set chatMessages(List<Message> value) {
    final List<String> messages = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('messages', messages);
  }

  bool get hasSpeakerProfile => getBool('hasSpeakerProfile') ?? false;

  set hasSpeakerProfile(bool value) => saveBool('hasSpeakerProfile', value);

  List<Plugin> get pluginsList {
    final List<String> plugins = getStringList('pluginsList') ?? [];
    return plugins.map((e) => Plugin.fromJson(jsonDecode(e))).toList();
  }

  set pluginsList(List<Plugin> value) {
    final List<String> plugins = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('pluginsList', plugins);
  }

  List<String> get pluginsEnabled => getStringList('pluginsEnabled') ?? [];

  set pluginsEnabled(List<String> value) => saveStringList('pluginsEnabled', value);

  enablePlugin(String value) {
    final List<String> plugins = pluginsEnabled;
    plugins.add(value);
    pluginsEnabled = plugins;
  }

  disablePlugin(String value) {
    final List<String> plugins = pluginsEnabled;
    plugins.remove(value);
    pluginsEnabled = plugins;
  }

  // List<int> get temporalAudioBytes {
  //   final List<String> bytes = getStringList('temporalAudioBytes') ?? [];
  //   return bytes.map((e) => int.parse(e)).toList();
  // }

  // set temporalAudioBytes(List<int> value) {
  //   final List<String> bytes = value.map((e) => e.toString()).toList();
  //   saveStringList('temporalAudioBytes', bytes);
  // }

  List<TranscriptSegment> get transcriptSegments {
    final List<String> segments = getStringList('transcriptSegments') ?? [];
    return segments.map((e) => TranscriptSegment.fromJson(jsonDecode(e))).toList();
  }

  set transcriptSegments(List<TranscriptSegment> value) {
    final List<String> segments = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('transcriptSegments', segments);
  }

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

  set scriptMemoriesToObjectBoxExecuted(bool value) => saveBool('scriptMemoriesToObjectBoxExecuted', value);

  bool get scriptMemoriesToObjectBoxExecuted => getBool('scriptMemoriesToObjectBoxExecuted') ?? false;
}

String getOpenAIApiKeyForUsage() =>
    SharedPreferencesUtil().useFriendApiKeys ? (Env.openAIAPIKey ?? '') : SharedPreferencesUtil().openAIApiKey;
