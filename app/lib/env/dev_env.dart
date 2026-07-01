import 'package:envied/envied.dart';

import 'env.dart';

part 'dev_env.g.dart';

// Every field in this file is compiled into public client binaries.
// Do not add provider API keys, OAuth client secrets, service accounts,
// private keys, admin tokens, signing credentials, or backend-only secrets.
@Envied(allowOptionalFields: true, path: '.client.dev.env')
final class DevEnv implements EnvFields {
  DevEnv();

  @override
  @EnviedField(varName: 'PUBLIC_POSTHOG_API_KEY', obfuscate: true)
  final String? posthogApiKey = _DevEnv.posthogApiKey;

  @override
  @EnviedField(varName: 'PUBLIC_API_BASE_URL', obfuscate: true)
  final String? apiBaseUrl = _DevEnv.apiBaseUrl;

  @override
  @EnviedField(varName: 'PUBLIC_GOOGLE_MAPS_API_KEY', obfuscate: true)
  final String? googleMapsApiKey = _DevEnv.googleMapsApiKey;

  @override
  @EnviedField(varName: 'PUBLIC_INTERCOM_APP_ID', obfuscate: true)
  final String? intercomAppId = _DevEnv.intercomAppId;

  @override
  @EnviedField(varName: 'PUBLIC_INTERCOM_IOS_API_KEY', obfuscate: true)
  final String? intercomIOSApiKey = _DevEnv.intercomIOSApiKey;

  @override
  @EnviedField(varName: 'PUBLIC_INTERCOM_ANDROID_API_KEY', obfuscate: true)
  final String? intercomAndroidApiKey = _DevEnv.intercomAndroidApiKey;

  @override
  @EnviedField(varName: 'PUBLIC_GOOGLE_CLIENT_ID', obfuscate: true)
  final String? googleClientId = _DevEnv.googleClientId;

  @override
  @EnviedField(varName: 'PUBLIC_USE_WEB_AUTH', obfuscate: false, defaultValue: false)
  final bool? useWebAuth = _DevEnv.useWebAuth;

  @override
  @EnviedField(varName: 'PUBLIC_USE_AUTH_CUSTOM_TOKEN', obfuscate: false, defaultValue: false)
  final bool? useAuthCustomToken = _DevEnv.useAuthCustomToken;

  @override
  @EnviedField(varName: 'PUBLIC_STAGING_API_URL', obfuscate: true)
  final String? stagingApiUrl = _DevEnv.stagingApiUrl;
}
