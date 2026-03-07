import 'package:envied/envied.dart';

import 'env.dart';

part 'dev_env.g.dart';

@Envied(allowOptionalFields: true, path: '.dev.env')
final class DevEnv implements EnvFields {
  DevEnv();

  @override
  @EnviedField(varName: 'OPENAI_API_KEY', obfuscate: true)
  final String? openAIAPIKey = _DevEnv.openAIAPIKey;

  @override
  @EnviedField(varName: 'MIXPANEL_PROJECT_TOKEN', obfuscate: true)
  final String? mixpanelProjectToken = _DevEnv.mixpanelProjectToken;

  @override
  @EnviedField(varName: 'API_BASE_URL', obfuscate: true)
  final String? apiBaseUrl = _DevEnv.apiBaseUrl;

  @override
  @EnviedField(varName: 'GROWTHBOOK_API_KEY', obfuscate: true)
  final String? growthbookApiKey = _DevEnv.growthbookApiKey;

  @override
  @EnviedField(varName: 'GOOGLE_MAPS_API_KEY', obfuscate: true)
  final String? googleMapsApiKey = _DevEnv.googleMapsApiKey;

  @override
  @EnviedField(varName: 'INTERCOM_APP_ID', obfuscate: true)
  final String? intercomAppId = _DevEnv.intercomAppId;

  @override
  @EnviedField(varName: 'INTERCOM_IOS_API_KEY', obfuscate: true)
  final String? intercomIOSApiKey = _DevEnv.intercomIOSApiKey;

  @override
  @EnviedField(varName: 'INTERCOM_ANDROID_API_KEY', obfuscate: true)
  final String? intercomAndroidApiKey = _DevEnv.intercomAndroidApiKey;

  @override
  @EnviedField(varName: 'GOOGLE_CLIENT_ID', obfuscate: true)
  final String? googleClientId = _DevEnv.googleClientId;

  @override
  @EnviedField(varName: 'GOOGLE_CLIENT_SECRET', obfuscate: true)
  final String? googleClientSecret = _DevEnv.googleClientSecret;

  @override
  @EnviedField(varName: 'USE_WEB_AUTH', obfuscate: false, defaultValue: false)
  final bool? useWebAuth = _DevEnv.useWebAuth;

  @override
  @EnviedField(varName: 'USE_AUTH_CUSTOM_TOKEN', obfuscate: false, defaultValue: false)
  final bool? useAuthCustomToken = _DevEnv.useAuthCustomToken;

  @override
  @EnviedField(varName: 'STAGING_API_URL', obfuscate: true)
  final String? stagingApiUrl = _DevEnv.stagingApiUrl;
}
