import 'dart:convert';
import 'package:friend_private/backend/storage/message.dart';
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
    if (!_preferences!.containsKey('uid')) {
      _preferences!.setString('uid', const Uuid().v4());
    }
  }

  String get uid => getString('uid') ?? '';

  String get openAIApiKey => getString('openaiApiKey') ?? '';

  set openAIApiKey(String value) => saveString('openaiApiKey', value);

  String get deepgramApiKey => getString('deepgramApiKey') ?? '';

  set deepgramApiKey(String value) => saveString('deepgramApiKey', value);

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

  List<Message> get chatMessages {
    final List<String> messages = getStringList('messages') ?? [];
    return messages.map((e) => Message.fromJson(jsonDecode(e))).toList();
  }

  set chatMessages(List<Message> value) {
    final List<String> messages = value.map((e) => jsonEncode(e.toJson())).toList();
    saveStringList('messages', messages);
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
}

String getOpenAIApiKeyForUsage() =>
    SharedPreferencesUtil().useFriendApiKeys ? (Env.openAIAPIKey ?? '') : SharedPreferencesUtil().openAIApiKey;

String getDeepgramApiKeyForUsage() =>
    SharedPreferencesUtil().useFriendApiKeys ? (Env.deepgramApiKey ?? '') : SharedPreferencesUtil().deepgramApiKey;
