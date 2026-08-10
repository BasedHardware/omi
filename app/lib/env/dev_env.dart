import 'package:envied/envied.dart';

import 'env.dart';

part 'dev_env.g.dart';

@Envied(allowOptionalFields: true, path: '.dev.env')
final class DevEnv implements EnvFields {
  DevEnv();

  @override
  @EnviedField(varName: 'POSTHOG_API_KEY', obfuscate: true)
  final String? posthogApiKey = _DevEnv.posthogApiKey;

  @override
  @EnviedField(varName: 'API_BASE_URL', obfuscate: true)
  final String? apiBaseUrl = _DevEnv.apiBaseUrl;

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

  // Additive OIDC client (ADR-0038). Default 'firebase' → existing flow untouched.
  @override
  @EnviedField(varName: 'AUTH_BACKEND', obfuscate: false, defaultValue: 'firebase')
  final String? authBackend = _DevEnv.authBackend;

  @override
  @EnviedField(varName: 'OIDC_ISSUER', obfuscate: false, defaultValue: '')
  final String? oidcIssuer = _DevEnv.oidcIssuer;

  @override
  @EnviedField(varName: 'OIDC_CLIENT_ID', obfuscate: false, defaultValue: '')
  final String? oidcClientId = _DevEnv.oidcClientId;

  @override
  @EnviedField(varName: 'OIDC_REDIRECT_SCHEME', obfuscate: false, defaultValue: '')
  final String? oidcRedirectScheme = _DevEnv.oidcRedirectScheme;

  // Client notification delivery backend (ADR-0011). Default 'fcm' → existing FCM/APNs push untouched.
  @override
  @EnviedField(varName: 'NOTIFICATIONS_BACKEND', obfuscate: false, defaultValue: 'fcm')
  final String? notificationsBackend = _DevEnv.notificationsBackend;
}
