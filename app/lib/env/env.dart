import 'package:omi/env/dev_env.dart';
import 'package:omi/utils/logger.dart';
import 'package:shared_preferences/shared_preferences.dart';

abstract class Env {
  static late final EnvFields _instance;
  static String? _customApiBaseUrl;
  static const String customApiBaseUrlKey = 'customApiBaseUrl';

  static Future<void> init([EnvFields? instance]) async {
    _instance = instance ?? DevEnv() as EnvFields;
    final prefs = await SharedPreferences.getInstance();
    _customApiBaseUrl = prefs.getString(customApiBaseUrlKey);

    // Log the initial API URL configuration
    Logger.debug('🔧 API Configuration: Initialized with base URL: ${_getEffectiveApiBaseUrl()}');
    if (_customApiBaseUrl != null && _customApiBaseUrl!.isNotEmpty) {
      Logger.debug('🔄 Using custom API base URL: $_customApiBaseUrl');
    }
  }

  static String? get openAIAPIKey => _instance.openAIAPIKey;

  static String? get instabugApiKey => _instance.instabugApiKey;

  static String? get mixpanelProjectToken => _instance.mixpanelProjectToken;

  // Helper method to get the effective API base URL
  static String _getEffectiveApiBaseUrl() {
    if (_customApiBaseUrl != null && _customApiBaseUrl!.isNotEmpty) {
      return _customApiBaseUrl!;
    }
    return _instance.apiBaseUrl ?? 'No API URL configured';
  }

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

    // Log server change
    String oldUrl = _getEffectiveApiBaseUrl();
    Logger.debug('🔄 Changing API server: $oldUrl -> $url');

    await prefs.setString(customApiBaseUrlKey, url);
    _customApiBaseUrl = url;

    Logger.debug('✅ API server changed successfully to: $url');
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
