import 'package:omi/env/dev_env.dart';
import 'package:shared_preferences/shared_preferences.dart';

abstract class Env {
  static late final EnvFields _instance;
  static String? _customApiBaseUrl;
  static const String customApiBaseUrlKey = 'customApiBaseUrl';

  static Future<void> init([EnvFields? instance]) async {
    _instance = instance ?? DevEnv() as EnvFields;
    final prefs = await SharedPreferences.getInstance();
    _customApiBaseUrl = prefs.getString(customApiBaseUrlKey);
  }

  static String? get openAIAPIKey => _instance.openAIAPIKey;

  static String? get instabugApiKey => _instance.instabugApiKey;

  static String? get mixpanelProjectToken => _instance.mixpanelProjectToken;

  static String? get apiBaseUrl {
    if (_customApiBaseUrl != null && _customApiBaseUrl!.isNotEmpty) {
      return _customApiBaseUrl;
    }
    return _instance.apiBaseUrl;
  }

  static String? get growthbookApiKey => _instance.growthbookApiKey;

  static String? get googleMapsApiKey => _instance.googleMapsApiKey;

  static String? get intercomAppId => _instance.intercomAppId;

  static String? get intercomIOSApiKey => _instance.intercomIOSApiKey;

  static String? get intercomAndroidApiKey => _instance.intercomAndroidApiKey;

  static String? get posthogApiKey => _instance.posthogApiKey;

  static Future<void> setCustomApiBaseUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(customApiBaseUrlKey, url);
    _customApiBaseUrl = url;
  }
}

abstract class EnvFields {
  String? get openAIAPIKey;

  String? get instabugApiKey;

  String? get mixpanelProjectToken;

  String? get apiBaseUrl;

  String? get growthbookApiKey;

  String? get googleMapsApiKey;

  String? get intercomAppId;

  String? get intercomIOSApiKey;

  String? get intercomAndroidApiKey;

  String? get posthogApiKey;
}
