import 'dart:convert';
import 'package:collection/collection.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/backend/schema/bt_device/bt_device.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/backend/schema/person.dart';
import 'package:friend_private/services/wals.dart';
import 'package:shared_preferences/shared_preferences.dart';

// This is a web-specific implementation of SharedPreferencesUtil
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

  // Implement the same interface as the non-web version
  // but with web-specific implementations where needed
  
  // Basic getters/setters remain the same
  set uid(String value) => saveString('uid', value);
  String get uid => getString('uid') ?? '';
  
  // User preferences
  set name(String value) => saveString('name', value);
  String get name => getString('name') ?? '';

  set email(String value) => saveString('email', value);
  String get email => getString('email') ?? '';

  set onboardingCompleted(bool value) => saveBool('onboardingCompleted', value);
  bool get onboardingCompleted => getBool('onboardingCompleted') ?? false;

  set lastActiveConversationId(String value) => saveString('lastActiveConversationId', value);
  String get lastActiveConversationId => getString('lastActiveConversationId') ?? '';

  set lastActivePersonaId(String value) => saveString('lastActivePersonaId', value);
  String get lastActivePersonaId => getString('lastActivePersonaId') ?? '';

  set lastActiveDeviceId(String value) => saveString('lastActiveDeviceId', value);
  String get lastActiveDeviceId => getString('lastActiveDeviceId') ?? '';

  set lastActiveAppId(String value) => saveString('lastActiveAppId', value);
  String get lastActiveAppId => getString('lastActiveAppId') ?? '';

  // Web-specific simplified implementations
  Future<bool> saveConversation(Conversation conversation) async {
    return true; // Simplified for web
  }

  Future<List<Conversation>> getConversations() async {
    return []; // Simplified for web
  }

  Future<bool> saveMessage(Message message) async {
    return true; // Simplified for web
  }

  Future<List<Message>> getMessages(String conversationId) async {
    return []; // Simplified for web
  }

  Future<bool> savePerson(Person person) async {
    return true; // Simplified for web
  }

  Future<List<Person>> getPeople() async {
    return []; // Simplified for web
  }

  Future<bool> saveDevice(BtDevice device) async {
    return true; // Simplified for web
  }

  Future<List<BtDevice>> getDevices() async {
    return []; // Simplified for web
  }

  Future<bool> saveApp(App app) async {
    return true; // Simplified for web
  }

  Future<List<App>> getApps() async {
    return []; // Simplified for web
  }

  // Helper methods
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

  Future<bool> saveStringList(String key, List<String> value) async {
    return await _preferences?.setStringList(key, value) ?? false;
  }

  List<String>? getStringList(String key) {
    return _preferences?.getStringList(key);
  }
}
