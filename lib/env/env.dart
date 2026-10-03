<content>
import 'package:shared_preferences/shared_preferences.dart';

class Env {
  static Env? _instance;
  static late SharedPreferences _prefs;

  // Default configuration
  static const String _defaultApiBaseUrl = 'https://api.omi.me';

  // Configuration values
  late String apiBaseUrl;
  late String sentryDsn;
  late bool isDebugMode;
  late bool isLocalDevelopment;

  Env._internal();

  static Future<Env> getInstance() async {
    if (_instance == null) {
      _instance = Env._internal();
      await _instance!._init();
    }
    return _instance!;
  }

  Future<void> _init() async {
    _prefs = await SharedPreferences.getInstance();
    
    // Load configuration with overrides
    apiBaseUrl = _prefs.getString('apiBaseUrlOverride') ?? _defaultApiBaseUrl;
    sentryDsn = _prefs.getString('sentryDsn') ?? '';
    isDebugMode = bool.tryParse(_prefs.getString('isDebugMode')?.toString() ?? 'false') ?? false;
    isLocalDevelopment = bool.tryParse(_prefs.getString('isLocalDevelopment')?.toString() ?? 'false') ?? false;
  }

  // Override methods
  static Future<void> overrideApiBaseUrl(String url) async {
    _apiBaseUrlOverride = url;
    await _prefs.setString('apiBaseUrlOverride', url);
  }

  static Future<void> resetApiBaseUrl() async {
    _apiBaseUrlOverride = null;
    await _prefs.remove('apiBaseUrlOverride');
  }

  // Internal state
  static String? _apiBaseUrlOverride;

  static String? get apiBaseUrl => _apiBaseUrlOverride ?? _instance?.apiBaseUrl;
}
</content>