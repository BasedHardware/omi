import 'package:envied/envied.dart';

import 'env.dart';

part 'prod_env.g.dart';

@Envied(allowOptionalFields: true, path: '.env')
final class ProdEnv implements EnvFields {
  ProdEnv();

  @override
  @EnviedField(varName: 'OPENAI_API_KEY', obfuscate: true)
  final String? openAIAPIKey = _ProdEnv.openAIAPIKey;

  @override
  @EnviedField(varName: 'MIXPANEL_PROJECT_TOKEN', obfuscate: true)
  final String? mixpanelProjectToken = _ProdEnv.mixpanelProjectToken;

  @override
  @EnviedField(varName: 'API_BASE_URL', obfuscate: true)
  final String? apiBaseUrl = _ProdEnv.apiBaseUrl;

  @override
  @EnviedField(varName: 'GROWTHBOOK_API_KEY', obfuscate: true)
  final String? growthbookApiKey = _ProdEnv.growthbookApiKey;

  @override
  @EnviedField(varName: 'GOOGLE_MAPS_API_KEY', obfuscate: true)
  final String? googleMapsApiKey = _ProdEnv.googleMapsApiKey;

  @override
  @EnviedField(varName: 'INTERCOM_APP_ID', obfuscate: true)
  final String? intercomAppId = _ProdEnv.intercomAppId;

  @override
  @EnviedField(varName: 'INTERCOM_IOS_API_KEY', obfuscate: true)
  final String? intercomIOSApiKey = _ProdEnv.intercomIOSApiKey;

  @override
  @EnviedField(varName: 'INTERCOM_ANDROID_API_KEY', obfuscate: true)
  final String? intercomAndroidApiKey = _ProdEnv.intercomAndroidApiKey;

  @override
  @EnviedField(varName: 'GOOGLE_CLIENT_ID', obfuscate: true)
  final String? googleClientId = _ProdEnv.googleClientId;

  @override
  @EnviedField(varName: 'GOOGLE_CLIENT_SECRET', obfuscate: true)
  final String? googleClientSecret = _ProdEnv.googleClientSecret;

  @override
  @EnviedField(varName: 'TODOIST_CLIENT_ID', obfuscate: true)
  final String? todoistClientId = _ProdEnv.todoistClientId;

  @override
  @EnviedField(varName: 'TODOIST_CLIENT_SECRET', obfuscate: true)
  final String? todoistClientSecret = _ProdEnv.todoistClientSecret;

  @override
  @EnviedField(varName: 'TODOIST_VERIFICATION_TOKEN', obfuscate: true)
  final String? todoistVerificationToken = _ProdEnv.todoistVerificationToken;

  @override
  @EnviedField(varName: 'ASANA_CLIENT_ID', obfuscate: true)
  final String? asanaClientId = _ProdEnv.asanaClientId;

  @override
  @EnviedField(varName: 'ASANA_CLIENT_SECRET', obfuscate: true)
  final String? asanaClientSecret = _ProdEnv.asanaClientSecret;

  @override
  @EnviedField(varName: 'GOOGLE_TASKS_CLIENT_ID', obfuscate: true)
  final String? googleTasksClientId = _ProdEnv.googleTasksClientId;

  @override
  @EnviedField(varName: 'GOOGLE_TASKS_CLIENT_SECRET', obfuscate: true)
  final String? googleTasksClientSecret = _ProdEnv.googleTasksClientSecret;

  @override
  @EnviedField(varName: 'CLICKUP_CLIENT_ID', obfuscate: true)
  final String? clickupClientId = _ProdEnv.clickupClientId;

  @override
  @EnviedField(varName: 'CLICKUP_CLIENT_SECRET', obfuscate: true)
  final String? clickupClientSecret = _ProdEnv.clickupClientSecret;
}
