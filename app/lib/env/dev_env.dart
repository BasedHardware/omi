import 'package:envied/envied.dart';

import 'env.dart';

part 'dev_env.g.dart';

@Envied(allowOptionalFields: true, path: '.env')
final class DevEnv implements EnvFields {
  DevEnv();

  @override
  @EnviedField(varName: 'OPENAI_API_KEY', obfuscate: true)
  final String? openAIAPIKey = _DevEnv.openAIAPIKey;

  @override
  @EnviedField(varName: 'INSTABUG_API_KEY', obfuscate: true)
  final String? instabugApiKey = _DevEnv.instabugApiKey;

  @override
  @EnviedField(varName: 'MIXPANEL_PROJECT_TOKEN', obfuscate: true)
  final String? mixpanelProjectToken = _DevEnv.mixpanelProjectToken;

  @override
  @EnviedField(varName: 'ONESIGNAL_APP_ID', obfuscate: true)
  final String? oneSignalAppId = _DevEnv.oneSignalAppId;

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
  @EnviedField(varName: 'RECHARGEAPP_API_KEY', obfuscate: true)
  final String? rechargeAppApiKey = _DevEnv.rechargeAppApiKey;
}
